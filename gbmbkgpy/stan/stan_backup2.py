import numpy as np
from scipy.interpolate import interp1d
import arviz as av
import matplotlib.pyplot as plt


class StanModelConstructor(object):
    """
    Object to construct the .stan model
    """

    def __init__(self, model_generator, profile=False):

        self._profile = profile
        
        data = model_generator.data
        model = model_generator.model

        num_dets = len(data.detectors)
        num_echans = len(data.echans)

        # Eff area correction?
        self._use_eff_area_correction = model._use_eff_area_correction
        
        # How many of which sources?

        # Global
        sources = model.global_sources
        self._num_fixed_global_sources = len(sources)
        if self._num_fixed_global_sources > 0:
            self._use_fixed_global_sources = True
        else:
            self._use_fixed_global_sources = False

        # Cont
        sources = model.continuum_sources
        self._num_cont_sources = int(len(sources) / num_echans)
        if self._num_cont_sources > 0:
            assert self._num_cont_sources == 2, "Must be two cont sources!"
            self._use_cont_sources = True
        else:
            self._use_cont_sources = False

        # SAA
        sources = model.saa_sources
        if len(sources)>0:
            self._use_saa = True
            self._dets_saa = model_generator._dets_saa
            if isinstance(self._dets_saa, str):
                num_dets_saa = num_dets
            else:
                num_dets_saa = len(self._dets_saa)
        else:
            self._use_saa = False

        if self._use_saa:
            self._num_saa_exits = int(len(sources) / (num_echans*num_dets_saa))
        else:
            self._num_saa_exits = 0
        #if self._num_saa_exits > 0:
        #    self._use_saa = True
        #else:
        #    self._use_saa = False

        # Free spectrum
        sources = model.fit_spectrum_sources
        self._num_free_ps = 0
        self._use_free_earth = False
        self._use_free_cgb = False
        self._use_sun = False
        for k in sources.keys():
            if k == "Earth occultation":
                self._use_free_earth = True
            elif k == "cgb":
                self._use_free_cgb = True
            elif k == "sun":
                self._use_sun = True
            else:
                self._num_free_ps += 1
        
        if self._num_free_ps > 0:
            self._use_free_ps = True
        else:
            self._use_free_ps = False

    def source_count(self):

        return dict(
            use_free_earth=self._use_free_earth,
            use_free_cgb=self._use_free_cgb,
            use_sun=self._use_sun,
            num_free_ps=self._num_free_ps,
            num_saa_exits=self._num_saa_exits,
            num_cont_sources=self._num_cont_sources,
            num_fixed_global_sources=self._num_fixed_global_sources,
        )

    def create_stan_file(self, save_path, total_only=False):

        if not total_only:
            text = (
                self.function_block()
                + self.data_block()
                + self.trans_data_block()
                + self.parameter_block()
                + self.trans_parameter_block()
                + self.model_block()
                + self.generated_block()
            )
        else:
            text = (
                self.function_block()
                + self.data_block()
                + self.trans_data_block()
                + self.parameter_block()
                + self.trans_parameter_block()
                + self.model_block()
                + self.generated_block_total_only()
            )

        with open(save_path, "w") as f:
            f.write(text)
            
    def function_block(self):
        text = "functions { \n"
        text += "\t#include powerlaw.stan\n"
        if self._use_saa:
            text += (
                "\tvector saa_total(vector[] saa_norm_vec, vector[] saa_decay_vec, matrix[] t_t0, int num_data_points,int num_saa_exits){\n"
                "\t\tvector[num_data_points] total_saa_counts = rep_vector(0.0, num_data_points);\n"
                "\t\tfor (i in 1:num_saa_exits){\n"
                "\t\t\ttotal_saa_counts += saa_norm_vec[i]./saa_decay_vec[i].*(exp(-t_t0[i,:,1].*saa_decay_vec[i]) - exp(-t_t0[i,:, 2].*saa_decay_vec[i, :]));\n"
                "\t\t}\n"
                "\t\treturn total_saa_counts;\n\t}\n\n"
            )
        # Main partial sum function
        main = "\treal partial_sum_lpmf(int[] counts, int start, int stop\n"

        if self._use_fixed_global_sources:
            main += "\t, vector[] base_counts_array, real[] norm_fixed\n"

        if self._use_free_earth:
            main += "\t, matrix base_response_array_earth, vector earth_spec\n"

        if self._use_free_cgb:
            main += "\t, matrix base_response_array_cgb, vector cgb_spec\n"

        if self._use_sun:
            main += "\t, matrix base_response_array_sun, vector sun_spec\n"
            
        if self._use_free_ps:
            main += "\t, matrix[] base_response_array_free_ps, vector[] ps_spec\n"

        if self._use_cont_sources:
            main += "\t, vector[] norm_cont_vec, vector[] base_counts_array_cont\n"

        if self._use_saa:
            main += "\t, matrix[] t_t0, vector[] saa_decay_vec, vector[] saa_norm_vec\n"

        if self._use_eff_area_correction:
            main += "\t, vector eff_area_array\n"
            
        main += "\t){\n"
        #if self._profile:                                                                                
        #    main += "\t\tprofile(\"loglike\"){\n"

        #poisson_lpmf
        main += "\t\treturn poisson_lupmf(counts | 0.00000001\n" # "\t\treturn poisson_propto_lpmf(counts | 0\n"
        
        if self._use_saa:
            for i in range(self._num_saa_exits):
                main += (
                    f"\t\t\t+saa_norm_vec[{i+1}, start:stop]./saa_decay_vec[{i+1}, start:stop].*"
                    f"(exp(-t_t0[{i+1},start:stop,1].*saa_decay_vec[{i+1}, start:stop])-"
                    f"exp(-t_t0[{i+1},start:stop,2].*saa_decay_vec[{i+1}, start:stop]))\n"
                )

        if self._use_fixed_global_sources:
            for i in range(self._num_fixed_global_sources):
                if self._use_eff_area_correction:
                    main += (
                        f"\t\t\t+eff_area_array[start:stop].*(norm_fixed[{i+1}]*base_counts_array[{i+1},start:stop])\n"
                    )
                else:
                    main += (
                        f"\t\t\t+norm_fixed[{i+1}]*base_counts_array[{i+1},start:stop]\n"
                    )

        if self._use_cont_sources:
            for i in range(self._num_cont_sources):
                main += f"\t\t\t+norm_cont_vec[{i+1}, start:stop].*base_counts_array_cont[{i+1}, start:stop]\n"

        if self._use_free_earth:
            if self._use_eff_area_correction:
                main += "\t\t\t+eff_area_array[start:stop].*(base_response_array_earth[start:stop]*earth_spec)\n"
            else:
                main += "\t\t\t+base_response_array_earth[start:stop]*earth_spec\n"

        if self._use_free_cgb:
            if self._use_eff_area_correction:
                main += "\t\t\t+eff_area_array[start:stop].*(base_response_array_cgb[start:stop]*cgb_spec)\n"
            else:
                main += "\t\t\t+base_response_array_cgb[start:stop]*cgb_spec\n"
                
        if self._use_sun:
            if self._use_eff_area_correction:
                main += "\t\t\t+eff_area_array[start:stop].*(base_response_array_sun[start:stop]*sun_spec)\n"
            else:
                main += "\t\t\t+base_response_array_sun[start:stop]*sun_spec\n"

        if self._use_free_ps:
            for i in range(self._num_free_ps):
                if self._use_eff_area_correction:
                    main += f"\t\t\t+eff_area_array[start:stop].*(base_response_array_free_ps[{i+1}, start:stop]*ps_spec[{i+1}])\n"
                else:
                    main += f"\t\t\t+base_response_array_free_ps[{i+1}, start:stop]*ps_spec[{i+1}]\n"

        main += "\t\t\t);\n"
        #if self._profile:
        #    main += "\t\t}\n"
        main += "\t}\n"


        text = text + main

        text += "\treal beuermann3(real E, real C, real index1, real index2, real index3, real Eb1, real Eb2, real n1, real n2){\n"
        text += "\t\treturn pow(pow(C*pow(Eb1, -index1)*pow(pow(E/Eb1, n1*index1)+pow(E/Eb1, n1*index2), -1/n1), -n2)+pow(C*pow(Eb1, -index1)*pow(pow(Eb2/Eb1, n1*index1)+pow(Eb2/Eb1, n1*index2), -1/n1)*pow(E/Eb2, -index3), -n2),-1/n2);\n"
        text += "\t}\n"
        
        
        text += "\treal beuermann2(real E, real C, real index1, real index2, real Eb1, real n1){\n"
        text += "\t\treturn C*pow(pow(E/Eb1, n1*index1)+pow(E/Eb1, n1*index2),-1/n1);\n"
        text += "\t}\n"
        text += "}\n\n"

        return text

    def data_block(self):
        # Start
        text = "data { \n"
        # This we need always:
        text += "\tint<lower=1> num_time_bins;\n"
        text += "\tint<lower=1> num_dets;\n"
        text += "\tint<lower=1> num_echans;\n"

        text += "\tint<lower=1> rsp_num_Ein;\n"
        text += "\tvector[rsp_num_Ein] Ebins_in[2];\n"

        text += "\tint<lower=1> grainsize;\n"
        text += "\tmatrix[num_time_bins, 2] time_bins;\n"

        text += "\tint counts[num_time_bins*num_dets*num_echans];\n"

        # Optional input
        if self._use_fixed_global_sources:
            text += "\tint<lower=0> num_fixed_comp;\n"
            text += "\tvector[num_time_bins*num_dets*num_echans] base_counts_array[num_fixed_comp];\n"
            text += "\tvector[num_fixed_comp] mu_norm_fixed;\n"
            text += "\tvector[num_fixed_comp] sigma_norm_fixed;\n"

        if self._use_cont_sources:
            text += "\tint num_cont_comp;\n"
            text += "\tvector[num_time_bins*num_dets*num_echans] base_counts_array_cont[num_cont_comp];\n"
            text += "\treal mu_norm_cont[num_cont_comp, num_dets, num_echans];\n"
            text += "\treal sigma_norm_cont[num_cont_comp, num_dets, num_echans];\n"

        if self._use_saa:
            text += "\tint num_saa_exits;\n"
            text += "\tvector[num_saa_exits] saa_start_times;\n"
            text += "\treal mu_norm_saa[num_saa_exits, num_dets, num_echans];\n"
            text += "\treal sigma_norm_saa[num_saa_exits, num_dets, num_echans];\n"
            text += "\treal mu_decay_saa[num_saa_exits, num_dets, num_echans];\n"
            text += "\treal sigma_decay_saa[num_saa_exits, num_dets, num_echans];\n"

            text += "\tint dets_saa[num_dets];\n"
            text += "\tint num_dets_saa;\n"
            text += "\tint dets_saa_all_dets[num_dets];\n"
        if self._use_free_ps:
            text += "\tint num_free_ps_comp;\n"
            text += "\tmatrix[num_echans*num_dets*num_time_bins, rsp_num_Ein] base_response_array_free_ps[num_free_ps_comp];\n"

        if self._use_sun:
            text += "\tmatrix[num_echans*num_dets*num_time_bins, rsp_num_Ein] base_response_array_sun;\n"
            
        if self._use_free_cgb:
            text += "\tmatrix[num_echans*num_dets*num_time_bins, rsp_num_Ein] base_response_array_cgb;\n"

        if self._use_free_earth:
            text += "\tmatrix[num_echans*num_dets*num_time_bins, rsp_num_Ein] base_response_array_earth;\n"

        # Close
        text = text + "}\n\n"
        return text

    def trans_data_block(self):
        text = "transformed data { \n"

        text += "\tint num_data_points = num_time_bins*num_dets*num_echans;\n"
        #text += "\treal Enorm = 30.0;\n"
        #text += "\treal b_cgb = 1.0;\n"
        #text += "\treal b_earth = 1.0;\n"
        if self._use_saa:
            text += "\tmatrix[num_data_points,2] t_t0[num_saa_exits];\n"
            text += (
                "\tfor (j in 1:num_saa_exits){\n"
                "\t\tfor (i in 1:num_time_bins){\n"
                "\t\t\tif (time_bins[i,1]>saa_start_times[j]){\n"
                "\t\t\t\tt_t0[j,(i-1)*num_dets*num_echans+1:i*num_dets*num_echans] = rep_matrix(time_bins[i]-saa_start_times[j], num_dets*num_echans);\n"
                "\t\t\t}\n"
                "\t\t\telse {\n"
                "\t\t\t\tt_t0[j,(i-1)*num_dets*num_echans+1:i*num_dets*num_echans] = rep_matrix(0.0, num_dets*num_echans, 2);\n"
                "\t\t\t}\n\t\t}\n\t}\n"
            )

        text = text + "}\n\n"
        return text

    def parameter_block(self):
        text = "parameters { \n"

        if self._use_fixed_global_sources:
            text += "\treal<lower=-10> log_norm_fixed[num_fixed_comp];\n"

        if self._use_saa:
            text += "\treal log_norm_saa[num_saa_exits, num_dets_saa, num_echans];\n"
            text += "\treal<lower=0.01,upper=10> decay_saa[num_saa_exits, num_dets_saa, num_echans];\n"


        if self._use_cont_sources:
            text += "\treal<lower=-6, upper=6> log_norm_cont[num_cont_comp, num_dets, num_echans];\n"

        if self._use_free_earth:
            
            text += "\treal<lower=-10, upper=5> log_norm_earth;\n"
            text += "\treal<lower=0, upper=6> beta_earth;\n"
            text += "\treal<lower=0, upper=8> n1_earth;\n"
            text += "\treal<lower=10, upper=100> Eb_earth;\n"
            #text += "\treal log_norm_earth;\n"
            #text += "\treal beta_earth;\n"
            #text += "\treal n1_earth;\n"
            #text += "\treal Eb_earth;\n"
            
            #text += "\treal<lower=0> n1_earth;\n"
            #text += "\treal<lower=0> Eb_earth;\n"
            #if True
            #    text += "\treal index_earth1;\n"
            #    text += "\treal index_earth2;\n"
            #    text += "\treal index_earth3;\n"
            #    text += "\treal index_earth4;\n"

            #    text += "\treal index_earth5;\n"
            #    text += "\treal index_earth6;\n"
            #    text += "\treal index_earth7;\n"
            #else:
            #    text += "\treal alpha_earth;\n"
            #    text += "\treal Ec_earth;\n"
            #    #text += "\treal<lower=0.1, upper=10> gamma_earth;\n"
            
            #text += "\treal Eb_earth;\n"
            #text += "\tordered[2] indices_earth;\n"
            #text += "\treal b_earth;\n"

        if self._use_free_cgb:
            text += "\treal<lower=-3, upper=3> log_norm_cgb;\n"
            if False:
                text += "\treal index_cgb1;\n"
                text += "\treal index_cgb2;\n"
                text += "\treal index_cgb3;\n"
                text += "\treal index_cgb4;\n"

                text += "\treal index_cgb5;\n"
                text += "\treal index_cgb6;\n"
                text += "\treal index_cgb7;\n"
                
            else:
                if False:
                    text += "\tordered[2] indices1_cgb;\n"
                    text += "\tordered[2] indices2_cgb;\n"
                    text += "\tordered[2] Ebs_cgb;\n"
                    #text += "\treal Eb_cgb;\n"
                    text += "\treal<lower=0> n1;\n"
                    text += "\treal<lower=0> n2;\n"
                    text += "\treal log_norm_cgb2;\n"
                else:
                    if False:
                        text += "\tordered[2] indices1_cgb;\n"
                        text += "\treal Eb_cgb;\n"
                        text += "\treal<lower=0> n1;\n"
                    else:
                        
                        text += "\treal<lower=0, upper=10> index1_cgb;\n"
                        text += "\treal<lower=0, upper=30> index_change12;\n"
                        #text += "\treal<lower=0, upper=3> index_change23;\n"


                        #text += "\treal<lower=0, upper=10> Eb_change12;\n"
                        text += "\treal<lower=5, upper=1000> Eb1_cgb;\n"


                        

                        # fix this
                        text += "\treal<lower=0, upper=10> n1;\n"
                        #text += "\treal<lower=0, upper=10> n2;\n"

                        #text += "\treal index1_cgb;\n"
                        #text += "\treal index_change12;\n"
                        #text += "\treal index_change23;\n"


                        #text += "\treal Eb_change12;\n"
                        #text += "\treal Eb1_cgb;\n"


                        #text += "\tvector[2] Ebs_cgb;\n"
                        
                        #text += "\treal n1;\n"
                        #text += "\treal n2;\n"

                    #text += "\tordered[2] indices_cgb;\n"
                    #text += "\treal beta_cgb;\n"
                    #text += "\treal Eb_cgb;\n"
                    #text += "\treal<lower=0.00001, upper=10> bs_cgb;\n"

            # third powerlaw
            #text += "\tordered[2] Ebs_cgb;\n" 
            #text += "\treal third_index_cgb;\n"

        if self._use_sun:
            text += "\treal log_norm_sun;\n"
            text += "\treal index_sun;\n"
            
        if self._use_free_ps:
            #text += "\treal log_norm_free_ps[num_free_ps_comp];\n"
            text += "\treal<lower=0, upper=10> index_free_ps[num_free_ps_comp];\n"
            text += "\treal<lower=-5> log_K_free_ps[num_free_ps_comp];\n"
        if self._use_eff_area_correction:
            #text += "\treal eff_area_corr[num_dets-1];\n"
            text += "\treal<lower=0, upper=2> eff_area_corr[num_dets-1];\n"
                        
        text = text + "}\n\n"
        return text

    def trans_parameter_block(self):
        text = "transformed parameters { \n"
        if self._profile:
            text+="\tprofile(\"transform_parameter\"){\n"
        if self._use_fixed_global_sources:
            text += "\treal norm_fixed[num_fixed_comp] = exp(log_norm_fixed);\n"

        if self._use_saa:
            text += "\treal norm_saa[num_saa_exits,num_dets_saa, num_echans]=exp(log_norm_saa);\n"

            text += "\tvector[num_data_points] saa_decay_vec[num_saa_exits];\n"
            text += "\tvector[num_data_points] saa_norm_vec[num_saa_exits];\n"

        if self._use_cont_sources:
            text += "\treal norm_cont[num_cont_comp, num_dets, num_echans] = exp(log_norm_cont);\n"
            text += "\tvector[num_data_points] norm_cont_vec[num_cont_comp];\n"

        if self._use_free_earth:
            text += "\treal norm_earth = exp(log_norm_earth);\n"
            text += "\tvector[rsp_num_Ein] earth_spec;\n"

        if self._use_free_cgb:
            text += "\treal norm_cgb = exp(log_norm_cgb);\n"
            text += "\tvector[rsp_num_Ein] cgb_spec;\n"

            text += "\treal C1_cgb;\n"
            text += "\treal index2_cgb=index1_cgb*(1+index_change12);\n"
            #text += "\treal index3_cgb=index2_cgb*(1+index_change23);\n"
            #text += "\treal Eb2_cgb=Eb1_cgb*(1+Eb_change12);\n"

            if False:
                text += "\treal norm_cgb2 = exp(log_norm_cgb2);\n"
                #text += "\treal n1=1.5;\n"
                #text += "\treal n2=1.5;\n"
                pass
            
            ###############                                                                                                                                                                                       
            #text += "\treal bs_cgb=1;\n"
            if not True:
                text += "\treal B = -0.5*(indices_cgb[1]+indices_cgb[2]);\n"
                text += "\treal M = -0.5*(indices_cgb[2]-indices_cgb[1]);\n"
                
                #text += "\treal alpha_cgb = 1.32;\n"
                #text += "\treal Eb_cgb = 30.0;\n"
                #text += "\treal B = -0.5*(alpha_cgb+beta_cgb);\n"
                #text += "\treal M = -0.5*(beta_cgb-alpha_cgb);\n"
                text += "\treal Mbs = M*bs_cgb;\n"
                text += "\treal arg_piv = log10(35.0/Eb_cgb)/bs_cgb;\n"
                text += "\treal ten_pcosh_piv;\n"
                text += "\treal pcosh1;\n"
                text += "\treal pcosh2;\n"
                text += "\treal arg1;\n"
                text += "\treal arg2;\n"

                #text += "\treal norm_third;\n"
                #text += "\treal arg_piv = log10(35.0/(Ebs_cgb[1]+25))/bs_cgb;\n"

        if self._use_free_ps:
            #text += "\treal norm_free_ps[num_free_ps_comp] = exp(log_norm_free_ps);\n"
            text += "\treal K_free_ps[num_free_ps_comp] = pow(10, log_K_free_ps);\n"
            text += "\tvector[rsp_num_Ein] ps_spec[num_free_ps_comp];\n"
            
        if self._use_sun:
            text += "\treal norm_sun = exp(log_norm_sun);\n"
            text += "\tvector[rsp_num_Ein] sun_spec;\n"

        if self._use_eff_area_correction:
            text += "\tvector[num_data_points] eff_area_array;\n"
            
        if self._use_cont_sources:
            text += (
                "\tfor (l in 1:num_cont_comp){\n"
                "\t\tfor (i in 1:num_dets){\n"
                "\t\t\tfor (j in 1:num_echans){\n"
                "\t\t\t\tfor (k in 1:num_time_bins){\n"
                "\t\t\t\t\tnorm_cont_vec[l][(k-1)*(num_dets*num_echans)+(i-1)*num_echans+j] = norm_cont[l,i,j];\n"
                "\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n"
            )

        if self._use_saa:
                
            text += (
                "\tfor (l in 1:num_saa_exits){\n"
                "\t\tfor (i in 1:num_dets){\n"
                "\t\t\tif (dets_saa[i]){\n"
                "\t\t\t\tfor (j in 1:num_echans){\n"
                "\t\t\t\t\tfor (k in 1:num_time_bins){\n"
                "\t\t\t\t\t\tsaa_decay_vec[l][(k-1)*(num_dets*num_echans)+(i-1)*num_echans+j] = 0.0001*decay_saa[l,dets_saa_all_dets[i],j];\n"#dets_saa_all_dets[i],j];\n"
                "\t\t\t\t\t\tsaa_norm_vec[l][(k-1)*(num_dets*num_echans)+(i-1)*num_echans+j] = norm_saa[l,dets_saa_all_dets[i],j];\n"#dets_saa_all_dets[i],j];\n"
                "\t\t\t\t\t}\n"
                "\t\t\t\t}\n"
                "\t\t\t}\n"
                
                "\t\t\telse {\n"
                "\t\t\t\tfor (j in 1:num_echans){\n"
                "\t\t\t\t\tfor (k in 1:num_time_bins){\n"
                "\t\t\t\t\t\tsaa_decay_vec[l][(k-1)*(num_dets*num_echans)+(i-1)*num_echans+j] = 1.0;\n"#dets_saa_all_dets[i],j];\n"
                "\t\t\t\t\t\tsaa_norm_vec[l][(k-1)*(num_dets*num_echans)+(i-1)*num_echans+j] = 0.0;\n"#dets_saa_all_dets[i],j];\n"
                "\t\t\t\t\t}\n"
                "\t\t\t\t}\n"
                "\t\t\t}\n"
                "\t\t}\n"
                "\t}\n"
                #"\tprint(saa_norm_vec);\n"
                #"\tprint(saa_decay_vec);\n"
            )

            #text += (

        if self._use_sun:
            text += (
                "\tfor (i in 1:rsp_num_Ein){\n"
                "\t\tsun_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*norm_sun*(pow((Ebins_in[1,i]/5.0), -index_sun)+pow((Ebins_in[2,i]/5.0), -index_sun))/2;\n"
                "\t}\n"
            )

            
        if self._use_free_ps:
            #text += (
            #    "\tfor (j in 1:num_free_ps_comp){\n"
            #    "\t\tfor (i in 1:rsp_num_Ein){\n"
            #    "\t\t\tps_spec[j][i] = (Ebins_in[2,i]-Ebins_in[1,i])*norm_free_ps[j]*(pow((Ebins_in[1,i]/35.0), -index_free_ps[j])+pow((Ebins_in[2,i]/35.0), -index_free_ps[j]))/2;\n"
            #    "\t\t}\n\t}\n"
            #)

            text += (
                "\tfor (j in 1:num_free_ps_comp){\n"
                "\t\tps_spec[j]=integrate_powerlaw_flux(Ebins_in, K_free_ps[j], index_free_ps[j]);\n"
                "\t}\n"
                )

        if self._use_free_earth:
            if True:
                text += (
                    "\tfor (i in 1:rsp_num_Ein){\n"
                    "\t\tearth_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*norm_earth*(1/(pow(Eb_earth,5)*pow(2.0,(-1.0/n1_earth)))*pow((pow(Ebins_in[1,i],(n1_earth*(-5)))+pow(Ebins_in[1,i],(n1_earth*beta_earth))*pow(Eb_earth,n1_earth*(-5-beta_earth))),-1.0/n1_earth)+1/(pow(Eb_earth,5)*pow(2.0,(-1.0/n1_earth)))*pow((pow(Ebins_in[2,i],(n1_earth*(-5)))+pow(Ebins_in[2,i],(n1_earth*beta_earth))*pow(Eb_earth,n1_earth*(-5-beta_earth))),-1.0/n1_earth));\n"
                    "\t}\n"
                )

                #text += (
                #    "\tfor (i in 1:rsp_num_Ein){\n"
                #    "\t\tearth_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*norm_earth*(1.0/(pow((Ebins_in[1,i]/33.7), -5)+pow((Ebins_in[1,i]/33.7), beta_earth))+1.0/(pow((Ebins_in[2,i]/33.7), -5)+pow((Ebins_in[2,i]/33.7), beta_earth)))/2;\n"
                #    "\t}\n"
                #)

                
                #text += (
                #    "\tfor (i in 1:rsp_num_Ein){\n"
                #    "\t\tearth_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*norm_earth*(1.0/(pow((Ebins_in[1,i]/33.7), -5)+pow((Ebins_in[1,i]/33.7), 1.72))+1.0/(pow((Ebins_in[2,i]/33.7), -5)+pow((Ebins_in[2,i]/33.7), 1.72)))/2;\n"
                #    "\t}\n"
                #)
                
                #text += (
                #    "\tfor (i in 1:rsp_num_Ein){\n"
                #    "\t\tif (Ebins_in[2,i]<40){"
                #    "\t\t\tearth_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*norm_earth*(pow((Ebins_in[1,i]/10.0), -index_earth)+pow((Ebins_in[2,i]/10.0), -index_earth))/2;\n"
                #    "\t\t}\n"
                #    "\t\telse {"
                #    "\t\t\tearth_spec[i] = 0;"
                #    "\t\t}\n"
                #    "\t}\n"
                #)
                
                #text += (
                #    "\tfor (i in 1:rsp_num_Ein){\n"
                #    "\t\tif (Ebins_in[1,i]<20){"
                #    "\t\t\tearth_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*norm_earth*(pow((Ebins_in[1,i]/10.0), -index_earth1)+pow((Ebins_in[2,i]/10.0), -index_earth1))/2;\n"
                #    "\t\t}\n"
                #    "\t\telse if (Ebins_in[1,i]<30){"
                #    "\t\t\tearth_spec[i] = norm_earth*pow((20.0/10.0), -index_earth1)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/20.0), -index_earth2)+pow((Ebins_in[2,i]/20.0), -index_earth2))/2;\n"
                #    "\t\t}\n"
                #    "\t\telse if (Ebins_in[1,i]<45){"
                #    "\t\t\tearth_spec[i] = norm_earth*pow((20.0/10.0), -index_earth1)*pow((30.0/20.0), -index_earth2)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/30.0), -index_earth3)+pow((Ebins_in[2,i]/30.0), -index_earth3))/2;\n"
                #    "\t\t}\n"
                #    "\t\telse if (Ebins_in[1,i]>45){"
                #    "\t\t\tearth_spec[i] = norm_earth*pow((20.0/10.0), -index_earth1)*pow((30.0/20.0), -index_earth2)*pow((45.0/30.0), -index_earth3)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/45.0), -index_earth4)+pow((Ebins_in[2,i]/45.0), -index_earth4))/2;\n"
                #    "\t\t}\n"
                #    "\t}\n"
                #    )

                #text += (
                #    "\tfor (i in 1:rsp_num_Ein){\n"
                #    "\t\tif (Ebins_in[1,i]<18){"
                #    "\t\t\tearth_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*norm_earth*(pow((Ebins_in[1,i]/10.0), -index_earth1)+pow((Ebins_in[2,i]/10.0), -index_earth1))/2;\n"
                #    "\t\t}\n"
                #    "\t\telse if (Ebins_in[1,i]<23){"
                #    "\t\t\tearth_spec[i] = norm_earth*pow((18.0/10.0), -index_earth1)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/18.0), -index_earth2)+pow((Ebins_in[2,i]/18.0), -index_earth2))/2;\n"
                #    "\t\t}\n"
                #    "\t\telse if (Ebins_in[1,i]<30){"
                #    "\t\t\tearth_spec[i] = norm_earth*pow((18.0/10.0), -index_earth1)*pow((23.0/18.0), -index_earth2)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/23.0), -index_earth3)+pow((Ebins_in[2,i]/23.0), -index_earth3))/2;\n"
                #    "\t\t}\n"
                #    "\t\telse if (Ebins_in[1,i]<37){"
                #    "\t\t\tearth_spec[i] = norm_earth*pow((18.0/10.0), -index_earth1)*pow((23.0/18.0), -index_earth2)*pow((30.0/23.0), -index_earth3)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/30.0), -index_earth4)+pow((Ebins_in[2,i]/30.0), -index_earth4))/2;\n"
                #    "\t\t}\n"
                #    "\t\telse if (Ebins_in[1,i]<45){"
                #    "\t\t\tearth_spec[i] = norm_earth*pow((18.0/10.0), -index_earth1)*pow((23.0/18.0), -index_earth2)*pow((30.0/23.0), -index_earth3)*pow((37.0/30.0), -index_earth4)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/37.0), -index_earth5)+pow((Ebins_in[2,i]/37.0), -index_earth5))/2;\n"
                #    "\t\t}\n"
                #    "\t\telse if (Ebins_in[1,i]<65){"
                #    "\t\t\tearth_spec[i] = norm_earth*pow((18.0/10.0), -index_earth1)*pow((23.0/18.0), -index_earth2)*pow((30.0/23.0), -index_earth3)*pow((37.0/30.0), -index_earth4)*pow((45.0/37.0), -index_earth5)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/45.0), -index_earth6)+pow((Ebins_in[2,i]/45.0), -index_earth6))/2;\n"
                #    "\t\t}\n"
                #    "\t\telse if (Ebins_in[1,i]>65){"
                #    "\t\t\tearth_spec[i] = norm_earth*pow((18.0/10.0), -index_earth1)*pow((23.0/18.0), -index_earth2)*pow((30.0/23.0), -index_earth3)*pow((37.0/30.0), -index_earth4)*pow((45.0/37.0), -index_earth5)*pow((65.0/45.0), -index_earth6)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/65.0), -index_earth7)+pow((Ebins_in[2,i]/65.0), -index_earth7))/2;\n"
                #    "\t\t}\n"
                #    "\t}\n"
                #    )
                
            else:
                text += (
                "\tfor (i in 1:rsp_num_Ein){\n"
                #"\t\tearth_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*norm_earth*(pow((Ebins_in[1,i]/35.0), -1*indices_earth[1])*pow(1+pow((Ebins_in[1,i]/Eb_earth), (indices_earth[2]-indices_earth[1])/b_earth), -1*b_earth)+pow((Ebins_in[2,i]/35.0), -1*indices_earth[1])*pow(1+pow((Ebins_in[2,i]/Eb_earth), (indices_earth[2]-indices_earth[1])/b_earth), -1*b_earth));\n"
                #"\t\tearth_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*norm_earth*(pow(Ebins_in[1,i], -alpha_earth)*exp(-Ec_earth/Ebins_in[1,i])+pow(Ebins_in[2,i], -alpha_earth)*exp(-Ec_earth/Ebins_in[2,i]));\n"
                # gamma=4 fixed
                "\t\tearth_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*norm_earth*(exp(log(Ebins_in[1,i]/35.0)*(-alpha_earth)-(Ec_earth/Ebins_in[1,i])*4)+exp(log(Ebins_in[2,i]/35.0)*(-alpha_earth)-(Ec_earth/Ebins_in[2,i])*4));\n"

                "\t}\n"
                )

        if self._use_free_cgb:

            if False:
                #text += (
                #    "\tfor (i in 1:rsp_num_Ein){\n"
                #    "\t\tif (Ebins_in[2,i]<40){"
                #    "\t\t\tcgb_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*norm_cgb*(pow((Ebins_in[1,i]/10.0), -index_cgb)+pow((Ebins_in[2,i]/10.0), -index_cgb))/2;\n"
                #    "\t\t}\n"
                #    "\t\telse {"
                #    "\t\t\tcgb_spec[i] = 0;"
                #    "\t\t}\n"
                #    "\t}\n"
                #)
                
                #text += (
                #    "\tfor (i in 1:rsp_num_Ein){\n"
                #    "\t\tif (Ebins_in[1,i]<20){"
                #    "\t\t\tcgb_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*norm_cgb*(pow((Ebins_in[1,i]/10.0), -index_cgb1)+pow((Ebins_in[2,i]/10.0), -index_cgb1))/2;\n"
                #    "\t\t}\n"
                #    "\t\telse if (Ebins_in[1,i]<30){"
                #    "\t\t\tcgb_spec[i] = norm_cgb*pow((20.0/10.0), -index_cgb1)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/20.0), -index_cgb2)+pow((Ebins_in[2,i]/20.0), -index_cgb2))/2;\n"
                #    "\t\t}\n"
                #    "\t\telse if (Ebins_in[1,i]<45){"
                #    "\t\t\tcgb_spec[i] = norm_cgb*pow((20.0/10.0), -index_cgb1)*pow((30.0/20.0), -index_cgb2)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/30.0), -index_cgb3)+pow((Ebins_in[2,i]/30.0), -index_cgb3))/2;\n"
                #    "\t\t}\n"
                #    "\t\telse if (Ebins_in[1,i]>45){"
                #    "\t\t\tcgb_spec[i] = norm_cgb*pow((20.0/10.0), -index_cgb1)*pow((30.0/20.0), -index_cgb2)*pow((45.0/30.0), -index_cgb3)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/45.0), -index_cgb4)+pow((Ebins_in[2,i]/45.0), -index_cgb4))/2;\n"
                #    "\t\t}\n"
                #    "\t}\n"
                #    )

                # 7 connected powerlaws. No curvature between PLs
                text += (
                    "\tfor (i in 1:rsp_num_Ein){\n"
                    "\t\tif (Ebins_in[1,i]<18){"
                    "\t\t\tcgb_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*norm_cgb*(pow((Ebins_in[1,i]/10.0), -index_cgb1)+pow((Ebins_in[2,i]/10.0), -index_cgb1))/2;\n"
                    "\t\t}\n"
                    "\t\telse if (Ebins_in[1,i]<23){"
                    "\t\t\tcgb_spec[i] = norm_cgb*pow((18.0/10.0), -index_cgb1)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/18.0), -index_cgb2)+pow((Ebins_in[2,i]/18.0), -index_cgb2))/2;\n"
                    "\t\t}\n"
                    "\t\telse if (Ebins_in[1,i]<30){"
                    "\t\t\tcgb_spec[i] = norm_cgb*pow((18.0/10.0), -index_cgb1)*pow((23.0/18.0), -index_cgb2)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/23.0), -index_cgb3)+pow((Ebins_in[2,i]/23.0), -index_cgb3))/2;\n"
                    "\t\t}\n"
                    "\t\telse if (Ebins_in[1,i]<37){"
                    "\t\t\tcgb_spec[i] = norm_cgb*pow((18.0/10.0), -index_cgb1)*pow((23.0/18.0), -index_cgb2)*pow((30.0/23.0), -index_cgb3)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/30.0), -index_cgb4)+pow((Ebins_in[2,i]/30.0), -index_cgb4))/2;\n"
                    "\t\t}\n"
                    "\t\telse if (Ebins_in[1,i]<45){"
                    "\t\t\tcgb_spec[i] = norm_cgb*pow((18.0/10.0), -index_cgb1)*pow((23.0/18.0), -index_cgb2)*pow((30.0/23.0), -index_cgb3)*pow((37.0/30.0), -index_cgb4)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/37.0), -index_cgb5)+pow((Ebins_in[2,i]/37.0), -index_cgb5))/2;\n"
                    "\t\t}\n"
                    "\t\telse if (Ebins_in[1,i]<65){"
                    "\t\t\tcgb_spec[i] = norm_cgb*pow((18.0/10.0), -index_cgb1)*pow((23.0/18.0), -index_cgb2)*pow((30.0/23.0), -index_cgb3)*pow((37.0/30.0), -index_cgb4)*pow((45.0/37.0), -index_cgb5)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/45.0), -index_cgb6)+pow((Ebins_in[2,i]/45.0), -index_cgb6))/2;\n"
                    "\t\t}\n"
                    "\t\telse if (Ebins_in[1,i]>65){"
                    "\t\t\tcgb_spec[i] = norm_cgb*pow((18.0/10.0), -index_cgb1)*pow((23.0/18.0), -index_cgb2)*pow((30.0/23.0), -index_cgb3)*pow((37.0/30.0), -index_cgb4)*pow((45.0/37.0), -index_cgb5)*pow((65.0/45.0), -index_cgb6)*(Ebins_in[2,i]-Ebins_in[1,i])*(pow((Ebins_in[1,i]/65.0), -index_cgb7)+pow((Ebins_in[2,i]/65.0), -index_cgb7))/2;\n"
                    "\t\t}\n"
                    "\t}\n"
                    )

            else:
                if True:
                    if False:
                        # broken powerlaw with variable curvature defined by n1
                        text += (
                            "\tfor (i in 1:rsp_num_Ein){\n"
                            "\t\tcgb_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*(norm_cgb/(pow(Ebs_cgb[1],-indices1_cgb[1])*pow(2.0,(-1.0/n1)))*pow((pow(Ebins_in[1,i],(n1*indices1_cgb[1]))+pow(Ebins_in[1,i],(n1*indices1_cgb[2]))*pow(Ebs_cgb[1],n1*(indices1_cgb[1]-indices1_cgb[2]))),-1.0/n1)+norm_cgb2/(pow(Ebs_cgb[2],-indices2_cgb[1])*pow(2.0,(-1.0/n2)))*pow((pow(Ebins_in[1,i],(n2*indices2_cgb[1]))+pow(Ebins_in[1,i],(n2*indices2_cgb[2]))*pow(Ebs_cgb[2],n2*(indices2_cgb[1]-indices2_cgb[2]))),-1.0/n2)+norm_cgb/(pow(Ebs_cgb[1],-indices1_cgb[1])*pow(2.0,(-1.0/n1)))*pow((pow(Ebins_in[2,i],(n1*indices1_cgb[1]))+pow(Ebins_in[2,i],(n1*indices1_cgb[2]))*pow(Ebs_cgb[1],n1*(indices1_cgb[1]-indices1_cgb[2]))),-1.0/n1)+norm_cgb2/(pow(Ebs_cgb[2],-indices2_cgb[1])*pow(2.0,(-1.0/n2)))*pow((pow(Ebins_in[2,i],(n2*indices2_cgb[1]))+pow(Ebins_in[2,i],(n2*indices2_cgb[2]))*pow(Ebs_cgb[2],n2*(indices2_cgb[1]-indices2_cgb[2]))),-1.0/n2));\n"
                            "\t}\n")
                    else:
                        if True:
                            # broken powerlaw with a parametrisation such that norm_cgb gives the flux at the peak and n1 gives curvature of break
                            text += (
                                "\tC1_cgb=norm_cgb*pow(pow(20.0/Eb1_cgb, n1*index1_cgb)+pow(20.0/Eb1_cgb, n1*index2_cgb),1/n1);\n"#norm_cgb*pow(2,1/n1);\n"
                                "\tfor (i in 1:rsp_num_Ein){\n"
                                "\t\tcgb_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*(beuermann2(Ebins_in[1,i], C1_cgb, index1_cgb, index2_cgb, Eb1_cgb, n1)+beuermann2(Ebins_in[2,i], C1_cgb, index1_cgb, index2_cgb, Eb1_cgb, n1));\n"
                                "\t}\n"

                                #"\tC1_cgb=norm_cgb;\n"
                                #"\tfor (i in 1:rsp_num_Ein){\n"
                                #"\t\tcgb_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*(beuermann2(Ebins_in[1,i], C1_cgb, index1_cgb, index2_cgb, Eb1_cgb, 1)+beuermann2(Ebins_in[2,i], C1_cgb, index1_cgb, index2_cgb, Eb1_cgb, 1));\n"
                                #"\t}\n"

                                
                            )
                        else:
                            text += (
                                "\tC1_cgb=norm_cgb*0.05*pow(Eb1_cgb, index1_cgb)*pow(pow(2,n2/n1)+pow(pow(Eb2_cgb/Eb1_cgb, n1*index1_cgb)+pow(Eb2_cgb/Eb1_cgb, n1*index2_cgb),n2/n1)*pow(Eb1_cgb/Eb2_cgb,n2*index3_cgb),1/n2);\n"

                                # use a function here
                                "\tfor (i in 1:rsp_num_Ein){\n"
                                "\t\tcgb_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*(beuermann3(Ebins_in[1,i], C1_cgb, index1_cgb, index2_cgb, index3_cgb, Eb1_cgb, Eb2_cgb, n1, n2)+beuermann3(Ebins_in[2,i], C1_cgb, index1_cgb, index2_cgb, index3_cgb, Eb1_cgb, Eb2_cgb, n1, n2));\n"
                                
                                "\t}\n"
                                )

                        #text += (
                        #    "\tfor (i in 1:rsp_num_Ein){\n"
                        #    "\t\tcgb_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*norm_cgb*(1/(pow((pow(Ebins_in[1,i],(n1*indices1_cgb[1]))+pow(Ebins_in[1,i],(n1*indices1_cgb[2]))*pow(Eb_cgb,n1*(indices1_cgb[1]-indices1_cgb[2]))),-1.0/n1)+ 1/(pow(Eb_cgb,-indices1_cgb[1])*pow(2.0,(-1.0/n1)))*pow((pow(Ebins_in[2,i],(n1*indices1_cgb[1]))+pow(Ebins_in[2,i],(n1*indices1_cgb[2]))*pow(Eb_cgb,n1*(indices1_cgb[1]-indices1_cgb[2]))),-1.0/n1));\n"
                        #    "\t}\n"
                        #)
                        
                else:
                    text += (
                        "\tif (arg_piv < -6.0){\n"
                        "\t\tten_pcosh_piv = pow(10, Mbs * (-arg_piv - log(2)));\n"
                        "\t}\n"
                        "\telse if (arg_piv > 4.0){\n"
                        "\t\tten_pcosh_piv = pow(10, Mbs * (arg_piv - log(2)));\n"
                        "\t}\n"
                        "\telse {\n"
                        "\t\tten_pcosh_piv = pow(10, Mbs*log((exp(arg_piv) + exp(-arg_piv)) / 2.0));\n"
                        "\t}\n"
                        "\tfor (i in 1:rsp_num_Ein){\n"
                        "\t\targ1 = log10(Ebins_in[1,i]/Eb_cgb)/bs_cgb;\n"
                        "\t\targ2 = log10(Ebins_in[2,i]/Eb_cgb)/bs_cgb;\n"
                        "\t\tif (arg1 < -6.0){\n"
                        "\t\t\tpcosh1 = Mbs * (-arg1 - log(2));\n"
                        "\t\t}\n"
                        "\t\telse if (arg1 > 4.0){\n"
                        "\t\t\tpcosh1 = Mbs * (arg1 - log(2));\n"
                        "\t\t}\n"
                        "\t\telse {\n"
                        "\t\t\tpcosh1 = Mbs * log(0.5 * ((exp(arg1) + exp(-arg1))));\n"
                        "\t\t}\n"
                        "\t\tif (arg2 < -6.0){\n"
                        "\t\t\tpcosh2 = Mbs * (-arg2 - log(2));\n"
                        "\t\t}\n"
                        "\t\telse if (arg2 > 4.0){\n"
                        "\t\t\tpcosh2 = Mbs * (arg2 - log(2));\n"
                        "\t\t}\n"
                        "\t\telse {\n"
                        "\t\t\tpcosh2 = Mbs * log(0.5 * ((exp(arg2) + exp(-arg2))));\n"
                        "\t\t}\n"
                        "\t\tcgb_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*(norm_cgb/ten_pcosh_piv)*(pow(Ebins_in[1,i]/35.0,B)*pow(10., pcosh1)+pow(Ebins_in[2,i]/35.0,B)*pow(10., pcosh2));\n"
                        "\t}\n"
                        ) 
                
                #"\targ1 = log10((Ebs_cgb[2]+25)/(Ebs_cgb[1]+25))/bs_cgb;\n"
                #"\tif (arg1 < -6.0){\n"
                #"\t\tpcosh1 = Mbs * (-arg1 - log(2));\n"
                #"\t}\n"
                #"\telse if (arg1 > 4.0){\n"
                #"\t\tpcosh1 = Mbs * (arg1 - log(2));\n"
                #"\t}\n"
                #"\telse {\n"
                #"\t\tpcosh1 = Mbs * log(0.5 * ((exp(arg1) + exp(-arg1))));\n"
                #"\t}\n"
                #"\tnorm_third = (norm_cgb/ten_pcosh_piv)*pow((Ebs_cgb[2]+25)/35.0,B)*pow(10., pcosh1);\n"
                #"\tfor (i in 1:rsp_num_Ein){\n"
                #"\t\tif (Ebins_in[2,i]<(Ebs_cgb[2]+25)){\n"
                #"\t\t\targ1 = log10(Ebins_in[1,i]/(Ebs_cgb[1]+25))/bs_cgb;\n"
                #"\t\t\targ2 = log10(Ebins_in[2,i]/(Ebs_cgb[1]+25))/bs_cgb;\n"
                #"\t\t\tif (arg1 < -6.0){\n"
                #"\t\t\t\tpcosh1 = Mbs * (-arg1 - log(2));\n"
                #"\t\t\t}\n"
                #"\t\t\telse if (arg1 > 4.0){\n"
                #"\t\t\t\tpcosh1 = Mbs * (arg1 - log(2));\n"
                #"\t\t\t}\n"
                #"\t\t\telse {\n"
                #"\t\t\t\tpcosh1 = Mbs * log(0.5 * ((exp(arg1) + exp(-arg1))));\n"
                #"\t\t\t}\n"
                #"\t\t\tif (arg2 < -6.0){\n"
                #"\t\t\t\tpcosh2 = Mbs * (-arg2 - log(2));\n"
                #"\t\t\t}\n"
                #"\t\t\telse if (arg2 > 4.0){\n"
                #"\t\t\t\tpcosh2 = Mbs * (arg2 - log(2));\n"
                #"\t\t\t}\n"
                #"\t\t\telse {\n"
                #"\t\t\t\tpcosh2 = Mbs * log(0.5 * ((exp(arg2) + exp(-arg2))));\n"
                #"\t\t\t}\n"
                #"\t\t\tcgb_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*(norm_cgb/ten_pcosh_piv)*(pow(Ebins_in[1,i]/35.0,B)*pow(10., pcosh1)+pow(Ebins_in[2,i]/35.0,B)*pow(10., pcosh2));\n"
                #"\t\t\tprint(cgb_spec[i]);\n"
                #"\t\t}\n"
                #"\t\telse {\n"
                #"\t\t\tcgb_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*norm_third*(pow((Ebins_in[1,i]/(Ebs_cgb[2]+25)), -third_index_cgb)+pow((Ebins_in[2,i]/(Ebs_cgb[2]+25)), -third_index_cgb));\n"
                #"\t\t}\n"

                #"\t\tcgb_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*norm_cgb*(pow((Ebins_in[1,i]/35.0), -1*indices_cgb[1])*pow(1+pow((Ebins_in[1,i]/Eb_cgb), (indices_cgb[2]-indices_cgb[1])/b_cgb), -1*b_cgb)+pow((Ebins_in[2,i]/35.0), -1*indices_cgb[1])*pow(1+pow((Ebins_in[2,i]/Eb_cgb), (indices_cgb[2]-indices_cgb[1])/b_cgb), -1*b_cgb));\n"
                #"\t\tcgb_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*(norm_cgb/(pow(Ebins_in[1,i]/Eb_cgb, indices_cgb[1])+pow(Ebins_in[1,i]/Eb_cgb, indices_cgb[2]))+norm_cgb/(pow(Ebins_in[2,i]/Eb_cgb, indices_cgb[1])+pow(Ebins_in[2,i]/Eb_cgb, indices_cgb[2])));\n"
                #"\t}\n"
                        #)

        if self._use_eff_area_correction:
            text += (
                "\tfor (i in 1:num_dets){\n"
                "\t\tfor (k in 1:num_time_bins){\n"
                "\t\t\tif (i==1){\n"
                "\t\t\t\teff_area_array[(k-1)*(num_dets*num_echans)+(i-1)*num_echans+1:(k-1)*(num_dets*num_echans)+i*num_echans] = rep_vector(1, num_echans);\n"
                "\t\t\t}\n"
                "\t\t\telse {\n"
                "\t\t\t\teff_area_array[(k-1)*(num_dets*num_echans)+(i-1)*num_echans+1:(k-1)*(num_dets*num_echans)+i*num_echans] = rep_vector(eff_area_corr[i-1], num_echans);\n"
                "\t\t\t}\n"
                "\t\t}\n"
                "\t}\n"
            )

            
        if self._profile:
            text += "\t}\n"

            
        text = text + "}\n\n"
        return text

    def model_block(self):
        text = "model { \n"

        """
        if self._profile:
            text+="\tprofile(\"transform_parameter\"){\n"
        if self._use_fixed_global_sources:
            text += "\treal norm_fixed[num_fixed_comp] = exp(log_norm_fixed);\n"

        if self._use_saa:
            text += "\treal norm_saa[num_saa_exits,num_dets_saa, num_echans]=exp(log_norm_saa);\n"

            text += "\tvector[num_data_points] saa_decay_vec[num_saa_exits];\n"
            text += "\tvector[num_data_points] saa_norm_vec[num_saa_exits];\n"

        if self._use_cont_sources:
            text += "\treal norm_cont[num_cont_comp, num_dets, num_echans] = exp(log_norm_cont);\n"
            text += "\tvector[num_data_points] norm_cont_vec[num_cont_comp];\n"

        if self._use_free_earth:
            text += "\treal norm_earth = exp(log_norm_earth);\n"
            text += "\tvector[rsp_num_Ein] earth_spec;\n"

        if self._use_free_cgb:
            text += "\treal norm_cgb = exp(log_norm_cgb);\n"
            text += "\tvector[rsp_num_Ein] cgb_spec;\n"

            text += "\treal C1_cgb;\n"
            text += "\treal index2_cgb=index1_cgb*(1+index_change12);\n"
            #text += "\treal index3_cgb=index2_cgb*(1+index_change23);\n"
            #text += "\treal Eb2_cgb=Eb1_cgb*(1+Eb_change12);\n"

        if self._use_free_ps:
            #text += "\treal norm_free_ps[num_free_ps_comp] = exp(log_norm_free_ps);\n"
            text += "\treal K_free_ps[num_free_ps_comp] = pow(10, log_K_free_ps);\n"
            text += "\tvector[rsp_num_Ein] ps_spec[num_free_ps_comp];\n"
            
        if self._use_sun:
            text += "\treal norm_sun = exp(log_norm_sun);\n"
            text += "\tvector[rsp_num_Ein] sun_spec;\n"

        if self._use_eff_area_correction:
            text += "\tvector[num_data_points] eff_area_array;\n"
            
        if self._use_cont_sources:
            text += (
                "\tfor (l in 1:num_cont_comp){\n"
                "\t\tfor (i in 1:num_dets){\n"
                "\t\t\tfor (j in 1:num_echans){\n"
                "\t\t\t\tfor (k in 1:num_time_bins){\n"
                "\t\t\t\t\tnorm_cont_vec[l][(k-1)*(num_dets*num_echans)+(i-1)*num_echans+j] = norm_cont[l,i,j];\n"
                "\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n"
            )

        if self._use_saa:
                
            text += (
                "\tfor (l in 1:num_saa_exits){\n"
                "\t\tfor (i in 1:num_dets){\n"
                "\t\t\tif (dets_saa[i]){\n"
                "\t\t\t\tfor (j in 1:num_echans){\n"
                "\t\t\t\t\tfor (k in 1:num_time_bins){\n"
                "\t\t\t\t\t\tsaa_decay_vec[l][(k-1)*(num_dets*num_echans)+(i-1)*num_echans+j] = 0.0001*decay_saa[l,dets_saa_all_dets[i],j];\n"#dets_saa_all_dets[i],j];\n"
                "\t\t\t\t\t\tsaa_norm_vec[l][(k-1)*(num_dets*num_echans)+(i-1)*num_echans+j] = norm_saa[l,dets_saa_all_dets[i],j];\n"#dets_saa_all_dets[i],j];\n"
                "\t\t\t\t\t}\n"
                "\t\t\t\t}\n"
                "\t\t\t}\n"
                
                "\t\t\telse {\n"
                "\t\t\t\tfor (j in 1:num_echans){\n"
                "\t\t\t\t\tfor (k in 1:num_time_bins){\n"
                "\t\t\t\t\t\tsaa_decay_vec[l][(k-1)*(num_dets*num_echans)+(i-1)*num_echans+j] = 1.0;\n"#dets_saa_all_dets[i],j];\n"
                "\t\t\t\t\t\tsaa_norm_vec[l][(k-1)*(num_dets*num_echans)+(i-1)*num_echans+j] = 0.0;\n"#dets_saa_all_dets[i],j];\n"
                "\t\t\t\t\t}\n"
                "\t\t\t\t}\n"
                "\t\t\t}\n"
                "\t\t}\n"
                "\t}\n"
                #"\tprint(saa_norm_vec);\n"
                #"\tprint(saa_decay_vec);\n"
            )

            #text += (

        if self._use_sun:
            text += (
                "\tfor (i in 1:rsp_num_Ein){\n"
                "\t\tsun_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*norm_sun*(pow((Ebins_in[1,i]/5.0), -index_sun)+pow((Ebins_in[2,i]/5.0), -index_sun))/2;\n"
                "\t}\n"
            )

            
        if self._use_free_ps:
            text += (
                "\tfor (j in 1:num_free_ps_comp){\n"
                "\t\tps_spec[j]=integrate_powerlaw_flux(Ebins_in, K_free_ps[j], index_free_ps[j]);\n"
                "\t}\n"
                )

        if self._use_free_earth:
            if True:
                text += (
                    "\tfor (i in 1:rsp_num_Ein){\n"
                    "\t\tearth_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*norm_earth*(1/(pow(Eb_earth,5)*pow(2.0,(-1.0/n1_earth)))*pow((pow(Ebins_in[1,i],(n1_earth*(-5)))+pow(Ebins_in[1,i],(n1_earth*beta_earth))*pow(Eb_earth,n1_earth*(-5-beta_earth))),-1.0/n1_earth)+1/(pow(Eb_earth,5)*pow(2.0,(-1.0/n1_earth)))*pow((pow(Ebins_in[2,i],(n1_earth*(-5)))+pow(Ebins_in[2,i],(n1_earth*beta_earth))*pow(Eb_earth,n1_earth*(-5-beta_earth))),-1.0/n1_earth));\n"
                    "\t}\n"
                )

        if self._use_free_cgb:
            if True:
                text += (
                    "\tC1_cgb=norm_cgb*pow(2,1/n1);\n"
                    "\tfor (i in 1:rsp_num_Ein){\n"
                    "\t\tcgb_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*(beuermann2(Ebins_in[1,i], C1_cgb, index1_cgb, index2_cgb, Eb1_cgb, n1)+beuermann2(Ebins_in[2,i], C1_cgb, index1_cgb, index2_cgb, Eb1_cgb, n1));\n"
                    "\t}\n"
                
                    #"\tC1_cgb=norm_cgb;\n"
                    #"\tfor (i in 1:rsp_num_Ein){\n"
                    #"\t\tcgb_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*(beuermann2(Ebins_in[1,i], C1_cgb, index1_cgb, index2_cgb, Eb1_cgb, 1)+beuermann2(Ebins_in[2,i], C1_cgb, index1_cgb, index2_cgb, Eb1_cgb, 1));\n"
                    #"\t}\n"
                                
                )
            else:
                text += (
                    "\tC1_cgb=norm_cgb*0.05*pow(Eb1_cgb, index1_cgb)*pow(pow(2,n2/n1)+pow(pow(Eb2_cgb/Eb1_cgb, n1*index1_cgb)+pow(Eb2_cgb/Eb1_cgb, n1*index2_cgb),n2/n1)*pow(Eb1_cgb/Eb2_cgb,n2*index3_cgb),1/n2);\n"
                    
                    # use a function here
                    "\tfor (i in 1:rsp_num_Ein){\n"
                    "\t\tcgb_spec[i] = (Ebins_in[2,i]-Ebins_in[1,i])*0.5*(beuermann3(Ebins_in[1,i], C1_cgb, index1_cgb, index2_cgb, index3_cgb, Eb1_cgb, Eb2_cgb, n1, n2)+beuermann3(Ebins_in[2,i], C1_cgb, index1_cgb, index2_cgb, index3_cgb, Eb1_cgb, Eb2_cgb, n1, n2));\n"
                                
                    "\t}\n"
                )


        if self._use_eff_area_correction:
            text += (
                "\tfor (i in 1:num_dets){\n"
                "\t\tfor (k in 1:num_time_bins){\n"
                "\t\t\tif (i==1){\n"
                "\t\t\t\teff_area_array[(k-1)*(num_dets*num_echans)+(i-1)*num_echans+1:(k-1)*(num_dets*num_echans)+i*num_echans] = rep_vector(1, num_echans);\n"
                "\t\t\t}\n"
                "\t\t\telse {\n"
                "\t\t\t\teff_area_array[(k-1)*(num_dets*num_echans)+(i-1)*num_echans+1:(k-1)*(num_dets*num_echans)+i*num_echans] = rep_vector(eff_area_corr[i-1], num_echans);\n"
                "\t\t\t}\n"
                "\t\t}\n"
                "\t}\n"
            )

            
        if self._profile:
            text += "\t}\n"
        """
        if self._profile:
            text += "\tprofile(\"priors\"){\n"
        
        # Priors - Fixed at the moment!:
        # TODO Use config file to get the priors!
        if self._use_fixed_global_sources:
            text += "\tlog_norm_fixed ~ normal(mu_norm_fixed, sigma_norm_fixed);\n"

        if self._use_free_earth:
            
            #if True:
            #    text += "\tindex_earth1 ~ normal(-5, 0.1);\n"
            #    text += "\tindex_earth2 ~ normal(-2, 0.1);\n"
            #    text += "\tindex_earth3 ~ normal(1, 0.1);\n"
            #    text += "\tindex_earth4 ~ normal(1.72, 0.1);\n"
            #    text += "\tindex_earth5 ~ normal(1.72, 0.1);\n"
            #    text += "\tindex_earth6 ~ normal(1.72, 0.1);\n"
            #    text += "\tindex_earth7 ~ normal(1.72, 0.1);\n"
            #else:
            #    text += "\talpha_earth ~ normal(1.72, 0.01);\n"
            #    text += "\tEc_earth ~ normal(30,2);\n"
            #    #text += "\tgamma_earth ~ lognormal(0,1);\n"
            
            text += "\tlog_norm_earth ~ normal(-5,3);\n"
            text += "\tbeta_earth ~ normal(1.72, 0.1);\n"

            text += "\tn1_earth ~ normal(1.5, 0.3);\n"
            text += "\tEb_earth ~ normal(30,5);\n"
            
            #text += "\tEb_earth ~ normal(30,2);\n"
            #text += "\tindices_earth[1] ~ normal(-5, 0.05);\n"
            #text += "\tindices_earth[2] ~ normal(1.72, 0.02);\n"
            #text += "\tb_earth ~ normal(1, 0.1);\n"
            
        if self._use_free_cgb:
            if False:
                text += "\tindex_cgb1 ~ normal(1.7, 0.05);\n"
                text += "\tindex_cgb2 ~ normal(2.0, 0.05);\n"
                text += "\tindex_cgb3 ~ normal(2.3, 0.05);\n"
                text += "\tindex_cgb4 ~ normal(2.88, 0.05);\n"
                text += "\tindex_cgb5 ~ normal(2.88, 0.05);\n"
                text += "\tindex_cgb6 ~ normal(2.88, 0.05);\n"
                text += "\tindex_cgb7 ~ normal(2.88, 0.05);\n"
            else:
                if False:
                    text += "\tindices1_cgb[1] ~ normal(1.32, 0.2);\n"
                    text += "\tindices1_cgb[2] ~ normal(2.88, 0.2);\n"
                    text += "\tindices2_cgb[1] ~ normal(1.32, 0.2);\n"
                    text += "\tindices2_cgb[2] ~ normal(2.88, 0.2);\n"
                    text += "\tEbs_cgb ~ normal(30,0.5);\n"
                    #text += "\tEb_cgb ~ normal(30,0.5);\n"
                    text += "\tlog_norm_cgb ~ normal(-3.2,1);\n"
                    text += "\tlog_norm_cgb2 ~ normal(-3.2,1);\n"
                    text += "\tn1 ~ normal(1.5, 0.3);\n"
                    text += "\tn2 ~ normal(1,0.3);\n"
                else:
                    if False:
                        text += "\tindices1_cgb[1] ~ normal(1.32, 0.2);\n"
                        text += "\tindices1_cgb[2] ~ normal(2.88, 0.2);\n"

                        text += "\tEb_cgb ~ normal(30,5);\n"
                        text += "\tlog_norm_cgb ~ normal(-3.2,1);\n"

                        
                        text += "\tn1 ~ normal(1.5, 0.3);\n"
                    else:                        
                        text += "\tindex1_cgb ~ normal(1.32, 0.2);\n"
                        text += "\tindex_change12 ~ lognormal(0, 1);\n"
                        #text += "\tindex_change23 ~ lognormal(0, 1);\n"

                        text += "\tEb1_cgb ~ normal(30,5);\n"
                        #text += "\tEb_change12 ~ lognormal(0,1);\n"
                        
                        #text += "\tEbs_cgb[1] ~ normal(30,5);\n"
                        #text += "\tEbs_cgb[2] ~ normal(100,20);\n"

                        text += "\tlog_norm_cgb ~ normal(0,0.5);\n"
                        # fix this
                        text += "\tn1 ~ normal(1.5, 0.3);\n"
                        #text += "\tn2 ~ normal(1.5, 0.3);\n"
                    #text += "\tindices_cgb[1] ~ normal(1.32, 0.05);\n"
                    #text += "\tindices_cgb[2] ~ normal(2.88, 0.0001);\n"
                    #text += "\tbeta_cgb ~ normal(2.88, 0.05);\n"
                    #text += "\tEb_cgb ~ normal(35,2);\n"
                    #text += "\tbs_cgb ~ lognormal(0, 1);\n"
                    #text += "\tlog_norm_cgb ~ normal(-4,2);\n"

                    #text += "\tEbs_cgb[1] ~ normal(35,2);\n"
                    #text += "\tEbs_cgb[2] ~ normal(100,20);\n"
                    #text += "\tthird_index_cgb ~ normal(2.88,0.5);\n"
                    #text += "\tbs_cgb ~ lognormal(0, 1);\n"
                    #text += "\tb_cgb ~ normal(1, 0.1);\n"
                    
        if self._use_sun:
            text += "\tindex_sun ~ normal(3,1);\n"
            text += "\tlog_norm_sun ~ normal(0,1);\n"

        if self._use_free_ps:
            text += "\tindex_free_ps ~ normal(3,1);\n"
            #text += "\tlog_norm_free_ps ~ normal(0,1);\n"
            text += "\tlog_K_free_ps ~ std_normal();\n"
        if self._use_cont_sources:
            text += (
                "\tfor (d in 1:num_dets){\n"
                "\t\tfor (g in 1:num_echans){\n"
                #"\t\t\tlog_norm_cont[:,d,g] ~ normal(mu_norm_cont[:,d,g], sigma_norm_cont[:,d,g]);\n"
                "\t\t\tlog_norm_cont[1,d,g] ~ normal(0, 0.1);\n"
                "\t\t\tlog_norm_cont[2,d,g] ~ std_normal();\n"
                "\t\t}\n\t}\n"
            )

        if self._use_eff_area_correction:
            text += "\teff_area_corr ~ uniform(0.8,1.2);\n"

        if self._use_saa:
            text += (
                "\tfor (d in 1:num_dets_saa){\n"
                "\t\tfor (e in 1:num_echans){\n"
                "\t\t\t\tlog_norm_saa[:,d,e] ~ normal(mu_norm_saa[:, d, e],sigma_norm_saa[:, d, e]);\n"
                "\t\t\t\tdecay_saa[:,d,e] ~ lognormal(mu_decay_saa[:, d, e],sigma_decay_saa[:, d, e]);\n"
                "\t\t}\n\t}\n"
            )


        #text += "\tprint(index_free_ps);\n"
        #text += "\tprint(log_K_free_ps);\n"
        #text += "\tprint(K_free_ps);\n"
        #text += "\tprint(C1_cgb);\n"
        #text += "\tprint(index1_cgb);\n"
        #text += "\tprint(index2_cgb);\n"
        #text += "\tprint(Eb1_cgb);\n"
        #text += "\tprint(Eb2_cgb);\n"
        #text += "\tprint(n1);\n"
        #text += "\tprint(n2);\n"
        #text += "\tprint(index3_cgb);\n"
        #text += "\tprint(cgb_spec);\n"
        #text += "\tprint(earth_spec);\n"
        #text += "\tprint(ps_spec);\n"
        #text += "\tprint(log_norm_fixed);\n"
        #text += "\tprint(norm_fixed);\n"
        #text += "\tprint(norm_cont_vec);\n"
        if self._profile:
            text += "\t}\n"
            text += "\tprofile(\"reduce_sum\"){\n"
        
        # Reduce sum call
        main = "\ttarget += reduce_sum(partial_sum_lpmf, counts, grainsize\n"
        #main = "\ttarget += partial_sum(counts, 1,size(counts)\n"
        if self._use_fixed_global_sources:
            main += "\t\t, base_counts_array, norm_fixed\n"

        if self._use_free_earth:
            main += "\t\t, base_response_array_earth, earth_spec\n"

        if self._use_free_cgb:
            main += "\t\t, base_response_array_cgb, cgb_spec\n"

        if self._use_sun:
            main += "\t\t, base_response_array_sun, sun_spec\n"
            
        if self._use_free_ps:
            main += "\t\t, base_response_array_free_ps, ps_spec\n"

        if self._use_cont_sources:
            main += "\t\t, norm_cont_vec,  base_counts_array_cont\n"

        if self._use_saa:
            main += "\t\t, t_t0, saa_decay_vec, saa_norm_vec\n"

        if self._use_eff_area_correction:
            main += "\t\t, eff_area_array\n"

        main += "\t);\n"
        if self._profile:
            main += "\t}\n" 
        text = text + main + "}\n\n"
        return text

    def generated_block(self):
        text = "generated quantities { \n"

        text += "\tint ppc[num_data_points];\n"
        text += "\tvector[num_data_points] tot=rep_vector(0.0, num_data_points);\n"

        if self._use_saa:
            text += "\tvector[num_data_points] f_saa;\n"

        if self._use_cont_sources:
            text += "\tvector[num_data_points] f_cont[num_cont_comp];\n"

        if self._use_fixed_global_sources:
            text += "\tvector[num_data_points] f_fixed_global[num_fixed_comp];\n"

        if self._use_free_earth:
            text += "\tvector[num_data_points] f_earth;\n"

        if self._use_free_cgb:
            text += "\tvector[num_data_points] f_cgb;\n"

        if self._use_sun:
            text += "\tvector[num_data_points] f_sun;\n"
            
        if self._use_free_ps:
            text += "\tvector[num_data_points] f_free_ps[num_free_ps_comp];\n"


            
        if self._use_saa:
            text += "\tf_saa = saa_total(saa_norm_vec, saa_decay_vec, t_t0, num_data_points, num_saa_exits);\n"
            text += "\ttot += f_saa;\n"

        if self._use_cont_sources:
            text += (
                "\tfor (i in 1:num_cont_comp){\n"
                "\t\tf_cont[i] = norm_cont_vec[i].*base_counts_array_cont[i];\n"
                "\t\ttot += f_cont[i];\n"
                "\t}\n"
            )

        if self._use_fixed_global_sources:
            if self._use_eff_area_correction:
                text += (
                    "\tfor (i in 1:num_fixed_comp){\n"
                    #"\t\tprint(eff_area_array);\n"
                    #"\t\tprint(norm_fixed[i]);\n"
                    #"\t\tprint(base_counts_array[i]);\n"
                    "\t\tf_fixed_global[i]=eff_area_array.*(norm_fixed[i]*base_counts_array[i]);\n"
                    "\t\ttot+=f_fixed_global[i];\n"
                    "\t}\n"
                )
                
            else:
                text += (
                    "\tfor (i in 1:num_fixed_comp){\n"
                    "\t\tf_fixed_global[i]=norm_fixed[i]*base_counts_array[i];\n"
                    "\t\ttot+=f_fixed_global[i];\n"
                    "\t}\n"
                )
                

        if self._use_free_earth:
            if self._use_eff_area_correction:
                text += "\tf_earth = eff_area_array.*(base_response_array_earth*earth_spec);\n"
            else:
                text += "\tf_earth = base_response_array_earth*earth_spec;\n"
            text += "\ttot += f_earth;\n"

        if self._use_free_cgb:
            if self._use_eff_area_correction:
                text += "\tf_cgb = eff_area_array.*(base_response_array_cgb*cgb_spec);\n"
            else:
                text += "\tf_cgb = base_response_array_cgb*cgb_spec;\n"
            text += "\ttot += f_cgb;\n"
            
        if self._use_sun:
            if self._use_eff_area_correction:
                text += "\tf_sun = eff_area_array.*(base_response_array_sun*sun_spec);\n"
            else:
                text += "\tf_sun = base_response_array_sun*sun_spec;\n"
            text += "\ttot += f_sun;\n"

        if self._use_free_ps:
            if self._use_eff_area_correction:
                text += (
                    "\tfor (i in 1:num_free_ps_comp){\n"
                    "\t\tf_free_ps[i]=eff_area_array.*(base_response_array_free_ps[i]*ps_spec[i]);\n"
                    "\t\ttot+=f_free_ps[i];\n"
                    "\t}\n"
                )
            else:
                text += (
                    "\tfor (i in 1:num_free_ps_comp){\n"
                    "\t\tf_free_ps[i]=base_response_array_free_ps[i]*ps_spec[i];\n"
                    "\t\ttot+=f_free_ps[i];\n"
                    "\t}\n"
                )
                
        text += "\tppc = poisson_rng(tot+0.000001);\n"

        text = text + "}\n\n"
        return text

    def generated_quantities(self):
        keys = []

        keys.append("tot")

        if self._use_cont_sources:
            keys.append("f_cont")

        if self._use_fixed_global_sources:
            keys.append("f_fixed_global")

        if self._use_free_earth:
            keys.append("f_earth")

        if self._use_free_cgb:
            keys.append("f_cgb")
            
        if self._use_sun:
            keys.append("f_sun")

        if self._use_free_ps:
            keys.append("f_free_ps")

        if self._use_saa:
            keys.append("f_saa")

        return keys

    def generated_block_total_only(self):
        text = "generated quantities { \n"

        text += "\tint ppc[num_data_points];\n"
        text += "\tvector[num_data_points] tot=rep_vector(0.0, num_data_points);\n"

        if self._use_saa:
            text += "\ttot += saa_total(saa_norm_vec, saa_decay_vec, t_t0, num_data_points, num_saa_exits);\n"

        if self._use_cont_sources:
            text += (
                "\tfor (i in 1:num_cont_comp){\n"
                "\t\ttot += norm_cont_vec[i].*base_counts_array_cont[i];\n"
                "\t}\n"
            )

        if self._use_fixed_global_sources:
            text += (
                "\tfor (i in 1:num_fixed_comp){\n"
                "\t\ttot +=norm_fixed[i]*base_counts_array[i];\n"
                "\t}\n"
            )

        if self._use_free_earth:
            text += "\ttot += base_response_array_earth*earth_spec;\n"

        if self._use_free_cgb:
            text += "\t tot+= base_response_array_cgb*cgb_spec;\n"
            
        if self._use_sun:
            text += "\t tot+= base_response_array_sun*sun_spec;\n"

        if self._use_free_ps:
            text += (
                "\tfor (i in 1:num_free_ps_comp){\n"
                "\t\ttot +=base_response_array_free_ps[i]*ps_spec[i];\n"
                "\t}\n"
            )

        text += "\tppc = poisson_rng(tot);\n"

        text = text + "}\n\n"
        return text


class StanDataConstructor(object):
    """
    Object to construct the data dictionary for stan!
    """

    def __init__(
        self,
        data=None,
        model=None,
        response=None,
        geometry=None,
        model_generator=None,
        threads_per_chain=1,
    ):
        """
        Init with data, model, response and geometry object or model_generator object
        """

        if model_generator is None:
            self._data = data
            self._model = model
            self._response = response
            self._geometry = geometry
        else:
            self._data = model_generator.data
            self._model = model_generator.model
            self._response = model_generator.response
            self._geometry = model_generator.geometry

            self._dets_saa = model_generator._dets_saa
            
        self._threads = threads_per_chain

        self._dets = self._data.detectors
        self._echans = self._data.echans
        self._total_time_bins = self._data.time_bins

        self._source_mask = np.ones(len(self._total_time_bins), dtype=bool)

        self.mask_source_intervals(model_generator.config.get("mask_intervals", []))

        self._time_bins = self._total_time_bins[self._source_mask]

        self._time_bin_edges = np.append(self._time_bins[:, 0], self._time_bins[-1, 1])

        self._ndets = len(self._dets)
        self._nechans = len(self._echans)
        self._ntimebins = len(self._time_bins)

        self._param_lookup = []

        self._global_param_names = None
        self._cont_param_names = None
        self._saa_param_names = None

    def mask_source_intervals(self, intervals):
        """
        This function mask the time intervals that contain a non-background source
        """

        for interval in intervals:

            bin_exclude = np.logical_and(
                self._total_time_bins[:, 0] > interval["start"],
                self._total_time_bins[:, 1] < interval["stop"],
            )

            self._source_mask[bin_exclude] = False

    def global_sources(self):
        """
        Fixed photon sources (e.g. point sources or CGB/Earth if spectrum not fitted)
        """

        s = self._model.global_sources

        if len(s) == 0:
            self._global_counts = None
            return None

        mu_norm_fixed = np.zeros(len(s))
        sigma_norm_fixed = np.zeros(len(s))
        global_counts = np.zeros((len(s), self._ntimebins, self._ndets, self._nechans))

        global_param_names = np.empty(len(s), dtype=object)

        for i, k in enumerate(s.keys()):
            global_counts[i] = s[k].get_counts(
                self._time_bins, bin_mask=self._source_mask
            )

            for p in s[k].parameters.values():

                if "norm" in p.name:
                    if p.gaussian_parameter[0] is not None:
                        mu_norm_fixed[i] = p.gaussian_parameter[0]
                    else:
                        mu_norm_fixed[i] = 0

                    if p.gaussian_parameter[1] is not None:
                        sigma_norm_fixed[i] = p.gaussian_parameter[1]
                    else:
                        sigma_norm_fixed[i] = 1

                    global_param_names[i] = p.name

                    self._param_lookup.append(
                        {
                            "name": p.name,
                            "idx_in_model": self._model.parameter_names.index(p.name),
                            "stan_param_name": f"norm_fixed[{i+1}]",
                            "scale": 1,
                        }
                    )
                else:
                    raise Exception("Unknown parameter name")

        # Flatten along time, detectors and echans
        global_counts = global_counts[:, 2:-2].reshape(len(s), -1)

        self._global_param_names = global_param_names
        self._global_counts = global_counts
        self._mu_norm_fixed = mu_norm_fixed
        self._sigma_norm_fixed = sigma_norm_fixed

    def continuum_sources(self):
        """
        Sources with an independent norm per echan and detector (Cosmic rays).
        At the moment hard coded for 2 sources (Constant and CosmicRay)
        """

        if len(self._model.continuum_sources) == 0:
            self._cont_counts = None
            return None

        # In the python code we have an individual source for every echan. For the stan code we need one in total.
        num_cont_sources = 2

        continuum_counts = np.zeros(
            (num_cont_sources, self._ntimebins, self._ndets, self._nechans)
        )

        cont_param_names = np.empty(
            (num_cont_sources, self._ndets, self._nechans), dtype=object
        )

        mu_norm_cont = np.zeros((num_cont_sources, self._ndets, self._nechans))
        sigma_norm_cont = np.zeros((num_cont_sources, self._ndets, self._nechans))
        
        for i, s in enumerate(list(self._model.continuum_sources.values())):
            if "constant" in s.name.lower():
                index = 0
            else:
                index = 1
            continuum_counts[index, :, :, s.echan] = s.get_counts(
                self._time_bins, bin_mask=self._source_mask
            )

            for p in s.parameters.values():

                if "norm" in p.name:
                    if p.gaussian_parameter[0] is not None:
                        mu_norm_cont[:, :, s.echan] = p.gaussian_parameter[0]
                    else:
                        mu_norm_cont[:, :, s.echan] = 0

                    if p.gaussian_parameter[1] is not None:
                        sigma_norm_cont[:, :, s.echan] = p.gaussian_parameter[1]
                    else:
                        sigma_norm_cont[:, :, s.echan] = 1

                    for det_idx, det in enumerate(self._dets):
                        self._param_lookup.append(
                            {
                                "name": f"{p.name}_{det}",
                                "idx_in_model": self._model.parameter_names.index(
                                    p.name
                                ),
                                "stan_param_name": f"norm_cont[{index+1},{det_idx + 1},{s.echan + 1}]",
                                "scale": 1,
                            }
                        )

                        cont_param_names[index, det_idx, s.echan] = f"{p.name}_{det}"
                else:
                    raise Exception("Unknown parameter name")

        self._cont_param_names = cont_param_names
        self._cont_counts = continuum_counts[:, 2:-2].reshape(2, -1)
        self._mu_norm_cont = mu_norm_cont
        self._sigma_norm_cont = sigma_norm_cont

    def free_spectrum_sources(self):
        """
        Free spectrum sources
        """

        s = self._model.fit_spectrum_sources

        self._Ebins_in = np.vstack(
            (
                self._response.responses[self._dets[0]].Ebin_in_edge[:-1],
                self._response.responses[self._dets[0]].Ebin_in_edge[1:],
            )
        )

        self._num_Ebins_in = len(self._Ebins_in[0])

        self._base_response_array_earth = None
        self._base_response_array_cgb = None
        self._base_response_array_sun = None
        self._base_response_array_ps = None

        if len(s) == 0:
            return None

        base_response_array_earth = None
        base_response_array_cgb = None
        base_response_array_sun = None
        base_rsp_ps_free = None

        for k in s.keys():
            rsp_detectors = s[k]._shape._effective_responses
            ar = np.zeros(
                (
                    self._ndets,
                    len(self._geometry.geometry_times),
                    self._num_Ebins_in,
                    self._nechans,
                )
            )
            for i, det in enumerate(self._dets):
                ar[i] = rsp_detectors[det]
            if k == "Earth occultation":
                base_response_array_earth = ar
            elif k == "cgb":
                base_response_array_cgb = ar
            elif k == "sun":
                base_response_array_sun = ar
            else:
                if base_rsp_ps_free is not None:
                    base_rsp_ps_free = np.append(
                        base_rsp_ps_free, np.array([ar]), axis=0
                    )
                else:
                    base_rsp_ps_free = np.array([ar])

        if base_response_array_earth is not None:

            eff_rsp_new_earth = interp1d(
                self._geometry.geometry_times, base_response_array_earth, axis=1
            )

            rsp_all_earth = np.swapaxes(
                np.array(
                    np.swapaxes(eff_rsp_new_earth(self._time_bin_edges), -1, -2),
                    dtype=float,
                ),
                0,
                1,
            )

            # Trapz integrate over time bins
            base_response_array_earth = (
                0.5
                * (
                    self._time_bins[:, 1, np.newaxis, np.newaxis, np.newaxis]
                    - self._time_bins[:, 0, np.newaxis, np.newaxis, np.newaxis]
                )
                * (rsp_all_earth[:-1] + rsp_all_earth[1:])
            )

            self._base_response_array_earth = base_response_array_earth[2:-2].reshape(
                -1, self._num_Ebins_in
            )

        if base_response_array_cgb is not None:

            eff_rsp_new_cgb = interp1d(
                self._geometry.geometry_times, base_response_array_cgb, axis=1
            )

            rsp_all_cgb = np.swapaxes(
                np.array(
                    np.swapaxes(eff_rsp_new_cgb(self._time_bin_edges), -1, -2),
                    dtype=float,
                ),
                0,
                1,
            )

            # Trapz integrate over time bins
            base_response_array_cgb = (
                0.5
                * (
                    self._time_bins[:, 1, np.newaxis, np.newaxis, np.newaxis]
                    - self._time_bins[:, 0, np.newaxis, np.newaxis, np.newaxis]
                )
                * (rsp_all_cgb[:-1] + rsp_all_cgb[1:])
            )

            self._base_response_array_cgb = base_response_array_cgb[2:-2].reshape(
                -1, self._num_Ebins_in
            )
            
        if base_response_array_sun is not None:

            eff_rsp_new_sun = interp1d(
                self._geometry.geometry_times, base_response_array_sun, axis=1
            )

            rsp_all_sun = np.swapaxes(
                np.array(
                    np.swapaxes(eff_rsp_new_sun(self._time_bin_edges), -1, -2),
                    dtype=float,
                ),
                0,
                1,
            )

            # Trapz integrate over time bins
            base_response_array_sun = (
                0.5
                * (
                    self._time_bins[:, 1, np.newaxis, np.newaxis, np.newaxis]
                    - self._time_bins[:, 0, np.newaxis, np.newaxis, np.newaxis]
                )
                * (rsp_all_sun[:-1] + rsp_all_sun[1:])
            )

            self._base_response_array_sun = base_response_array_sun[2:-2].reshape(
                -1, self._num_Ebins_in
            )

        if base_rsp_ps_free is not None:
            eff_rsp_new_free_ps = interp1d(
                self._geometry.geometry_times, base_rsp_ps_free, axis=2
            )

            rsp_all_ps = np.swapaxes(
                np.array(
                    np.swapaxes(eff_rsp_new_free_ps(self._time_bin_edges), -1, -2),
                    dtype=float,
                ),
                1,
                2,
            )

            # Trapz integrate over time bins
            base_rsp_ps_free = (
                0.5
                * (
                    self._time_bins[:, 1, np.newaxis, np.newaxis, np.newaxis]
                    - self._time_bins[:, 0, np.newaxis, np.newaxis, np.newaxis]
                )
                * (rsp_all_ps[:, :-1] + rsp_all_ps[:, 1:])
            )

            self._base_response_array_ps = base_rsp_ps_free[:, 2:-2].reshape(
                base_rsp_ps_free.shape[0], -1, self._num_Ebins_in
            )

    def saa_sources(self):
        """
        The Saa exit sources
        """
        # One source per exit (not per exit and echan like in the python code)
        self._num_saa_exits = int(len(self._model.saa_sources) / self._nechans)
                
        mu_norm_saa = np.zeros((self._num_saa_exits, self._ndets, self._nechans))
        sigma_norm_saa = np.zeros((self._num_saa_exits, self._ndets, self._nechans))
        mu_decay_saa = np.zeros((self._num_saa_exits, self._ndets, self._nechans))
        sigma_decay_saa = np.zeros((self._num_saa_exits, self._ndets, self._nechans))

        saa_start_times = np.zeros(self._num_saa_exits)

        saa_param_names = np.empty(
            (self._num_saa_exits, self._ndets, self._nechans), dtype=object
        )

        for i, s in enumerate(
            list(self._model.saa_sources.values())[: self._num_saa_exits]
        ):
            saa_start_times[i] = s._shape._saa_exit_time[0]

        for i, s in enumerate(list(self._model.saa_sources.values())):

            source_index = i % self._num_saa_exits

            if s._shape._det_idx is None:
                det_idx = np.arange(0, self._ndets)
                det_idx_stan = 1
            else:
                # TODO: Fix me.
                #raise Exception(
                #    "You selected decay per detector in the config which causes"
                #    "problems in the stan instantiation instantiation"
                #)
                det_idx = s._shape._det_idx
                det_idx_stan = det_idx + 1

            for d_idx, d in enumerate(self._dets):
                saa_param_names[source_index, d_idx, s.echan] = f"{s.name}_{d}"

            for p in s.parameters.values():

                if "norm" in p.name:
                    if p.gaussian_parameter[0] is not None:
                        mu_norm_saa[:, det_idx, s.echan] = p.gaussian_parameter[0]
                    else:
                        mu_norm_saa[:, det_idx, s.echan] = 0

                    if p.gaussian_parameter[1] is not None:
                        sigma_norm_saa[:, det_idx, s.echan] = p.gaussian_parameter[1]
                    else:
                        sigma_norm_saa[:, det_idx, s.echan] = 1

                    self._param_lookup.append(
                        {
                            "name": p.name,
                            "idx_in_model": self._model.parameter_names.index(p.name),
                            "stan_param_name": f"norm_saa[{source_index+1},{det_idx_stan},{s.echan+1}]",
                            "scale": 1,
                        }
                    )

                elif "decay" in p.name:
                    if p.gaussian_parameter[0] is not None:
                        mu_decay_saa[:, det_idx, s.echan] = p.gaussian_parameter[0]
                    else:
                        mu_decay_saa[:, det_idx, s.echan] = 0

                    if p.gaussian_parameter[1] is not None:
                        sigma_decay_saa[:, det_idx, s.echan] = p.gaussian_parameter[1]

                    else:
                        sigma_decay_saa[:, det_idx, s.echan] = 1

                    self._param_lookup.append(
                        {
                            "name": p.name,
                            "idx_in_model": self._model.parameter_names.index(p.name),
                            "stan_param_name": f"decay_saa[{source_index+1},{det_idx_stan},{s.echan+1}]",
                            "scale": 0.0001,
                        }
                    )
                else:
                    raise Exception("Unknown parameter name")

        self._saa_param_names = saa_param_names
        self._saa_start_times = saa_start_times
        self._mu_norm_saa = mu_norm_saa
        self._sigma_norm_saa = sigma_norm_saa
        self._mu_decay_saa = mu_decay_saa
        self._sigma_decay_saa = sigma_decay_saa

    def construct_data_dict(self):
        self.global_sources()
        self.continuum_sources()
        self.saa_sources()
        self.free_spectrum_sources()

        data_dict = {}

        data_dict["num_dets"] = self._ndets
        data_dict["num_echans"] = self._nechans

        counts = np.array(
            self._data.counts[self._source_mask][2:-2], dtype=int
        ).flatten()
        mask_zeros = (
            np.array(self._data.counts[self._source_mask][2:-2], dtype=int).flatten()
            != 0
        )

        data_dict["counts"] = np.array(
            self._data.counts[self._source_mask][2:-2], dtype=int
        ).flatten()[mask_zeros]
        data_dict["time_bins"] = self._time_bins[2:-2][
            mask_zeros[:: self._ndets * self._nechans]
        ]
        data_dict["num_time_bins"] = len(data_dict["time_bins"])

        data_dict["rsp_num_Ein"] = self._num_Ebins_in
        data_dict["Ebins_in"] = self._Ebins_in

        # Global sources
        if self._global_counts is not None:
            data_dict["num_fixed_comp"] = len(self._global_counts)
            data_dict["base_counts_array"] = self._global_counts[:, mask_zeros]
            data_dict["mu_norm_fixed"] = self._mu_norm_fixed
            data_dict["sigma_norm_fixed"] = self._sigma_norm_fixed
        #else:
        #    raise NotImplementedError

        if self._base_response_array_ps is not None:
            data_dict["num_free_ps_comp"] = len(self._base_response_array_ps)
            data_dict["base_response_array_free_ps"] = self._base_response_array_ps[
                :, mask_zeros
            ]
        if self._base_response_array_earth is not None:
            data_dict["base_response_array_earth"] = self._base_response_array_earth[
                mask_zeros
            ]
        if self._base_response_array_cgb is not None:
            data_dict["base_response_array_cgb"] = self._base_response_array_cgb[
                mask_zeros
            ]
        if self._base_response_array_sun is not None:
            data_dict["base_response_array_sun"] = self._base_response_array_sun[
                mask_zeros
            ]

        if self._base_response_array_cgb is not None:
            data_dict["earth_cgb_free"] = 1
        else:
            data_dict["earth_gb_free"] = 0

        if len(self._model.saa_sources) > 0:
            data_dict["num_saa_exits"] = self._num_saa_exits
            data_dict["saa_start_times"] = self._saa_start_times
            data_dict["mu_norm_saa"] = self._mu_norm_saa
            data_dict["sigma_norm_saa"] = self._sigma_norm_saa
            data_dict["mu_decay_saa"] = self._mu_decay_saa
            data_dict["sigma_decay_saa"] = self._sigma_decay_saa

            if isinstance(self._dets_saa, str):
                data_dict["dets_saa"] = np.ones(self._ndets, dtype=int)
                data_dict["num_dets_saa"] = self._ndets
                data_dict["dets_saa_all_dets"] = np.arange(1, self._ndets+1)
            else:
                dets_saa_mask = np.zeros(self._ndets, dtype=int)
                dets_saa_all_dets = np.zeros(self._ndets, dtype=int)
                n = 0
                for i, d in enumerate(self._dets_saa):
                    idx = np.argwhere(d==np.array(self._dets))[0,0]
                    dets_saa_mask[idx] = 1

                    dets_saa_all_dets[idx] = i+1
                    
                data_dict["dets_saa"] = dets_saa_mask
                data_dict["num_dets_saa"] = int(np.sum(dets_saa_mask))
                data_dict["dets_saa_all_dets"] = dets_saa_all_dets
            
        if self._cont_counts is not None:
            data_dict["num_cont_comp"] = 2
            data_dict["base_counts_array_cont"] = self._cont_counts[:, mask_zeros]
            data_dict["mu_norm_cont"] = self._mu_norm_cont
            data_dict["sigma_norm_cont"] = self._sigma_norm_cont
            
        # Stan grainsize for reduced_sum
        if self._threads == 1:
            data_dict["grainsize"] = 1
        else:
            data_dict["grainsize"] = 1
            #int(
            #    (self._ntimebins - 4) * self._ndets * self._nechans / self._threads
            #)
        return data_dict

    @property
    def param_lookup(self):
        return self._param_lookup

    @property
    def global_param_names(self):
        return self._global_param_names

    @property
    def cont_param_names(self):
        return self._cont_param_names

    @property
    def saa_param_names(self):
        return self._saa_param_names


class ReadStanArvizResult(object):
    def __init__(self, nc_files):
        for i, nc_file in enumerate(nc_files):
            if i == 0:
                self._arviz_result = av.from_netcdf(nc_file)
            else:
                self._arviz_result = av.concat(
                    self._arviz_result, av.from_netcdf(nc_file), dim="chain"
                )

        self._model_parts = self._arviz_result.predictions.keys()

        self._dets = self._arviz_result.constant_data["dets"].values
        self._echans = self._arviz_result.constant_data["echans"].values

        self._ndets = len(self._dets)
        self._nechans = len(self._echans)

        self._time_bins = self._arviz_result.constant_data["time_bins"].values
        self._time_bins -= self._time_bins[0, 0]
        self._bin_width = self._time_bins[:, 1] - self._time_bins[:, 0]

        self._counts = self._arviz_result.observed_data["counts"].values

        predictions = self._arviz_result.predictions.stack(sample=("chain", "draw"))
        self._parts = {}
        for key in self._model_parts:
            self._parts[key] = predictions[key].values

        self._ppc = self._arviz_result.posterior_predictive.stack(
            sample=("chain", "draw")
        )["ppc"].values

    def ppc_plots(self, save_dir):

        colors = {
            "f_fixed": "red",
            "f_free_ps": "red",
            "f_saa": "navy",
            "f_cont": "magenta",
            "f_earth": "purple",
            "f_cgb": "cyan",
            "f_sun": "black",
            "tot": "green",
        }

        for d_index, d in enumerate(self._dets):
            for e_index, e in enumerate(self._echans):

                mask = np.arange(len(self._counts), dtype=int)[
                    e_index + d_index * self._nechans :: self._ndets * self._nechans
                ]
                fig, ax = plt.subplots()

                ppc_min = np.percentile(self._ppc[mask], 5, axis=1)/ self._bin_width
                ppc_max = np.percentile(self._ppc[mask], 95, axis=1)/ self._bin_width

                ax.fill_between(np.mean(self._time_bins, axis=1),
                                y1=ppc_min,
                                y2=ppc_max,
                                color="darkgreen",
                                label="PPC",
                                alpha=0.3)

                for key in self._parts.keys():
                    if len(self._parts[key].shape) == 3:
                        for k in range(len(self._parts[key])):
                            part_min = np.percentile(self._parts[key][k][mask], 5, axis=1)/ self._bin_width
                            part_max = np.percentile(self._parts[key][k][mask], 95, axis=1)/ self._bin_width
                            if k==0:
                                ax.fill_between(np.mean(self._time_bins, axis=1),
                                                y1=part_min,
                                                y2=part_max,
                                                color=colors.get(key, "gray"),
                                                label=key,
                                                alpha=0.3)
                            else:
                                ax.fill_between(np.mean(self._time_bins, axis=1),
                                                y1=part_min,
                                                y2=part_max,
                                                color=colors.get(key, "gray"),
                                                alpha=0.3)
                    else:
                        part_min = np.percentile(self._parts[key][mask], 5, axis=1)/ self._bin_width
                        part_max = np.percentile(self._parts[key][mask], 95, axis=1)/ self._bin_width

                        ax.fill_between(np.mean(self._time_bins, axis=1),
                                            y1=part_min,
                                            y2=part_max,
                                            color=colors.get(key, "gray"),
                                            label=key,
                                            alpha=0.3)
                """
                for i in np.linspace(0, self._ppc.shape[1] - 1, 30, dtype=int):
                    
                    if i == 0:
                        ax.scatter(
                            np.mean(self._time_bins, axis=1),
                            self._ppc[mask][:, i] / self._bin_width,
                            color="darkgreen",
                            alpha=0.025,
                            edgecolor="darkgreen",
                            facecolor="none",
                            lw=0.9,
                            s=2,
                            label="PPC",
                        )
                    else:
                        ax.scatter(
                            np.mean(self._time_bins, axis=1),
                            self._ppc[mask][:, i] / self._bin_width,
                            color="darkgreen",
                            alpha=0.025,
                            edgecolor="darkgreen",
                            facecolor="none",
                            lw=0.9,
                            s=2,
                        )
                    
                    for key in self._parts.keys():
                        # Check if there are several sources in this class
                        if len(self._parts[key].shape) == 3:
                            for k in range(len(self._parts[key])):
                                if k == 0 and i == 0:
                                    ax.scatter(
                                        np.mean(self._time_bins, axis=1),
                                        self._parts[key][k][mask][:, i]
                                        / self._bin_width,
                                        alpha=0.025,
                                        edgecolor=colors.get(key, "gray"),
                                        facecolor="none",
                                        lw=0.9,
                                        s=2,
                                        label=key,
                                    )
                                else:
                                    ax.scatter(
                                        np.mean(self._time_bins, axis=1),
                                        self._parts[key][k][mask][:, i]
                                        / self._bin_width,
                                        alpha=0.025,
                                        edgecolor=colors.get(key, "gray"),
                                        facecolor="none",
                                        lw=0.9,
                                        s=2,
                                    )
                        else:
                            if i == 0:
                                ax.scatter(
                                    np.mean(self._time_bins, axis=1),
                                    self._parts[key][mask][:, i] / self._bin_width,
                                    alpha=0.025,
                                    edgecolor=colors.get(key, "gray"),
                                    facecolor="none",
                                    lw=0.9,
                                    s=2,
                                    label=key,
                                )
                            else:
                                ax.scatter(
                                    np.mean(self._time_bins, axis=1),
                                    self._parts[key][mask][:, i] / self._bin_width,
                                    alpha=0.025,
                                    edgecolor=colors.get(key, "gray"),
                                    facecolor="none",
                                    lw=0.9,
                                    s=2,
                                )
                """
                ax.scatter(
                    np.mean(self._time_bins, axis=1),
                    self._counts[mask] / self._bin_width,
                    color="darkgreen",
                    alpha=1,
                    edgecolor="black",
                    facecolor="none",
                    lw=0.9,
                    s=4,
                    label="Data",
                )
                # box = ax.get_position()
                # ax.set_position([box.x0, box.y0, box.width*0.7, box.height])
                lgd = fig.legend(loc="center left", bbox_to_anchor=(1.04, 0.5))
                for lh in lgd.legendHandles:
                    lh.set_alpha(1)
                t = fig.suptitle(f"Detector {d} - Echan {e}")
                fig.savefig(
                    f"ppc_result_det_{d}_echan_{e}.png",
                    bbox_extra_artists=(lgd,t)
                )  # , bbox_extra_artists=(lgd,t), dpi=450, bbox_inches='tight')
