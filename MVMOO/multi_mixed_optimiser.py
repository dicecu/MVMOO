import numpy as np
from scipy.stats import norm
from .mixed_optimiser import MVO
from scipy.optimize import shgo, differential_evolution, dual_annealing
import scipy as stats

class MVMOO(MVO):
    """
    Multi variate mixed variable optimisation
    """
    def __init__(self, input_dim=1, num_qual=0, num_obj=2, bounds=None, k_type='matern3', dist='manhattan', scale='bounds'):
        """
        Initialisation of the class
        """
        super().__init__(input_dim=input_dim, num_qual=num_qual, bounds=bounds, dist=dist, k_type=k_type)

        self.num_obj = num_obj
        self.scale = scale


    def generatemodels(self, X, Y, scale=True, variance=1.0):
        """
        Generate a list containing the models for each of the objectives
        """
        self.nsamples, nobj = np.shape(Y)
        models = []
        if scale is True:
            self.Yscaled = self.scaley(Y)
            self.Xscaled = self.scaleX(X,mode=self.scale)
            for i in range(nobj):
                self.fitmodel(self.Xscaled, self.Yscaled[:,i].reshape((-1,1)), variance=variance)
                models.append(self.model)
            return models
        for i in range(nobj):
            self.fitmodel(X, Y[:,i].reshape((-1,1)))
            models.append(self.model)
            return models

    def is_pareto_efficient(self, costs, return_mask = True):
        """
        Find the pareto-efficient points for minimisation problem
        :param costs: An (n_points, n_costs) array
        :param return_mask: True to return a mask
        :return: An array of indices of pareto-efficient points.
            If return_mask is True, this will be an (n_points, ) boolean array
            Otherwise it will be a (n_efficient_points, ) integer array of indices.
        """
        is_efficient = np.arange(costs.shape[0])
        n_points = costs.shape[0]
        next_point_index = 0  # Next index in the is_efficient array to search for
        while next_point_index<len(costs):
            nondominated_point_mask = np.any(costs<costs[next_point_index], axis=1)
            nondominated_point_mask[next_point_index] = True
            is_efficient = is_efficient[nondominated_point_mask]  # Remove dominated points
            costs = costs[nondominated_point_mask]
            next_point_index = np.sum(nondominated_point_mask[:next_point_index])+1
        if return_mask:
            is_efficient_mask = np.zeros(n_points, dtype = bool)
            is_efficient_mask[is_efficient] = True
            return is_efficient_mask
        else:
            return is_efficient

    def paretofront(self, Y):
        """
        Return an array of the pareto front for the system, set up for a minimising
        """
        ind = self.is_pareto_efficient(Y, return_mask=False)
        return Y[ind,:]

    def EIM(self, X, mode='euclidean'):
        """
        Calculate the expected improvment matrix for a candidate point

        @ARTICLE{7908974, 
            author={D. {Zhan} and Y. {Cheng} and J. {Liu}}, 
            journal={IEEE Transactions on Evolutionary Computation}, 
            title={Expected Improvement Matrix-Based Infill Criteria for Expensive Multiobjective Optimization}, 
            year={2017}, 
            volume={21}, 
            number={6}, 
            pages={956-975}, 
            doi={10.1109/TEVC.2017.2697503}, 
            ISSN={1089-778X}, 
            month={Dec}}
        """
        f = self.currentfront

        nfx = np.shape(f)[0]
    
        nobj = np.shape(f)[1]
    
        nx = np.shape(X)[0]
    
        r = 1.1 * np.ones((1, nobj))
        y = np.zeros((nx, 1))
    
        ulist = []
        varlist = []

        X = self.scaleX(X, mode='bounds')
    
        for iobj in range(nobj):
            u, var = self.models[iobj].predict_y(X)
            ulist.append(u)
            varlist.append(var)
            
        u = np.concatenate(ulist, axis=1)
        var = np.concatenate(varlist, axis=1)
        std = np.sqrt(np.maximum(0,var))

        u_matrix = np.reshape(u.T,(1,nobj,nx)) * np.ones((nfx,1,1))
        s_matrix = np.reshape(std.T,(1,nobj,nx)) * np.ones((nfx,1,1))
        f_matrix = f.reshape((nfx,nobj,1)) * np.ones((1,1,nx))
        Z_matrix = (f_matrix - u_matrix) / s_matrix
        EI_matrix = np.multiply((f_matrix - u_matrix), norm.cdf(Z_matrix)) + np.multiply(s_matrix, norm.pdf(Z_matrix))
        if mode == 'euclidean':
            y = np.min(np.sqrt(np.sum(EI_matrix**2,axis=1)),axis=0).reshape(-1,1)
        elif mode == 'hypervolume':
            y = np.min(np.prod(r.reshape(1,2,1)  - f_matrix + EI_matrix, axis=1) - np.prod(r - f, axis=1).reshape((-1,1)),axis=0).reshape((-1,1))
        elif mode == 'maxmin':
            y = np.min(np.max(EI_matrix,axis=1),axis=0).reshape(-1,1)
        elif mode == 'combine':
            y = np.min(np.sqrt(np.sum(EI_matrix**2,axis=1)),axis=0).reshape(-1,1) +\
                 np.min(np.prod(r.reshape(1,2,1)  - f_matrix + EI_matrix, axis=1) - \
                     np.prod(r - f, axis=1).reshape((-1,1)),axis=0).reshape((-1,1))
        else:
            y1 = np.min(np.sqrt(np.sum(EI_matrix**2,axis=1)),axis=0).reshape(-1,1)
            y2 = np.min(np.prod(r.reshape(1,2,1)  - f_matrix + EI_matrix, axis=1) - np.prod(r - f, axis=1).reshape((-1,1)),axis=0).reshape((-1,1))
            #y3 = np.min(np.max(EI_matrix,axis=1),axis=0).reshape(-1,1)
            return np.hstack((y1,y2))

        return y

    def CEIM_Hypervolume(self, X):
        """
        Calculate the expected improvment matrix for a candidate point, given constraints

        @ARTICLE{7908974, 
            author={D. {Zhan} and Y. {Cheng} and J. {Liu}}, 
            journal={IEEE Transactions on Evolutionary Computation}, 
            title={Expected Improvement Matrix-Based Infill Criteria for Expensive Multiobjective Optimization}, 
            year={2017}, 
            volume={21}, 
            number={6}, 
            pages={956-975}, 
            doi={10.1109/TEVC.2017.2697503}, 
            ISSN={1089-778X}, 
            month={Dec}}
        """
        f = self.currentfront
    
        nobj = np.shape(f)[1]
    
        nx = np.shape(X)[0]
    
        r = 1.1 * np.ones((1, nobj))
        y = np.zeros((nx, 1))
    
        ulist = []
        varlist = []
    
        for iobj in range(nobj):
            u, var = self.models[iobj].predict_y(X)
            ulist.append(u)
            varlist.append(var)
            
        u = np.concatenate(ulist, axis=1)
        var = np.concatenate(varlist, axis=1)
        std = np.sqrt(np.maximum(0,var))
    
        for ix in range(nx):
            Z = (f - u[ix,:]) / std[ix,:]
            EIM = np.multiply((f - u[ix,:]), norm.cdf(Z)) + np.multiply(std[ix,:], norm.pdf(Z))
            y[ix] = np.min(np.prod(r - f + EIM, axis=1) - np.prod(r - f, axis=1))
        
        # Constraints
        ncon = len(self.constrainedmodels)

        uconlist = []
        varconlist = []
    
        for iobj in range(ncon):
            ucon, varcon = self.constrainedmodels[iobj].predict_y(X)
            uconlist.append(ucon)
            varconlist.append(varcon)
            
        ucon = np.concatenate(uconlist, axis=1)
        varcon = np.concatenate(varconlist, axis=1)
        stdcon = np.sqrt(np.maximum(0,varcon))

        PoF = np.prod(norm.cdf((0 - ucon) / stdcon), axis=1).reshape(-1,1)

        return y * PoF

    def AEIM_Hypervolume(self, X):
        """
        Calculate the  adaptive expected improvment matrix for a candidate point

        Adaptive addition based on https://arxiv.org/pdf/1807.01279.pdf
        """
        f = self.currentfront
        c = self.contextual

        nfx = np.shape(f)[0]
    
        nobj = np.shape(f)[1]
    
        nx = np.shape(X)[0]
    
        r = 1.1 * np.ones((1, nobj))
        y = np.zeros((nx, 1))
    
        ulist = []
        varlist = []
    
        for iobj in range(nobj):
            u, var = self.models[iobj].predict_y(X)
            ulist.append(u)
            varlist.append(var)
            
        u = np.concatenate(ulist, axis=1)
        var = np.concatenate(varlist, axis=1)
        std = np.sqrt(np.maximum(0,var))

        u_matrix = np.reshape(u.T,(1,nobj,nx)) * np.ones((nfx,1,1))
        s_matrix = np.reshape(std.T,(1,nobj,nx)) * np.ones((nfx,1,1))
        f_matrix = f.reshape((nfx,nobj,1)) * np.ones((1,1,nx))
        c_matrix = c.reshape((nfx,nobj,1)) * np.ones((1,1,nx))
        Z_matrix = (f_matrix - u_matrix - c_matrix) / s_matrix
        EI_matrix = np.multiply((f_matrix - u_matrix), norm.cdf(Z_matrix)) + np.multiply(s_matrix, norm.pdf(Z_matrix))
        y = np.min(np.prod(r.reshape(1,2,1)  - f_matrix + EI_matrix, axis=1) - np.prod(r - f, axis=1).reshape((-1,1)),axis=0).reshape((-1,1))
    
        #for ix in range(nx):
        #    Z = (f - u[ix,:] - c) / std[ix,:]
        #    EIM = np.multiply((f - u[ix,:]), norm.cdf(Z)) + np.multiply(std[ix,:], norm.pdf(Z))
        #    y[ix] = np.min(np.prod(r - f + EIM, axis=1) - np.prod(r - f, axis=1))
        
        return y

    def AEIM_Euclidean(self, X):
        """
        Calculate the expected improvment matrix for a candidate point

        @ARTICLE{7908974, 
            author={D. {Zhan} and Y. {Cheng} and J. {Liu}}, 
            journal={IEEE Transactions on Evolutionary Computation}, 
            title={Expected Improvement Matrix-Based Infill Criteria for Expensive Multiobjective Optimization}, 
            year={2017}, 
            volume={21}, 
            number={6}, 
            pages={956-975}, 
            doi={10.1109/TEVC.2017.2697503}, 
            ISSN={1089-778X}, 
            month={Dec}}
        """
        f = self.currentfront
        c = self.contextual

        nfx = np.shape(f)[0]
    
        nobj = np.shape(f)[1]
    
        nx = np.shape(X)[0]

        y = np.zeros((nx, 1))
    
        ulist = []
        varlist = []
        X = self.scaleX(X, mode='bounds')
    
        for iobj in range(nobj):
            u, var = self.models[iobj].predict_f(X)
            ulist.append(u)
            varlist.append(var)
            
        u = np.concatenate(ulist, axis=1)
        var = np.concatenate(varlist, axis=1)
        std = np.sqrt(np.maximum(0,var))

        u_matrix = np.reshape(u.T,(1,nobj,nx)) * np.ones((nfx,1,1))
        s_matrix = np.reshape(std.T,(1,nobj,nx)) * np.ones((nfx,1,1))
        f_matrix = f.reshape((nfx,nobj,1)) * np.ones((1,1,nx))
        c_matrix = c.reshape((nfx,nobj,1)) * np.ones((1,1,nx))
        Z_matrix = (f_matrix - u_matrix - c_matrix) / s_matrix
        EI_matrix = np.multiply((f_matrix - u_matrix), norm.cdf(Z_matrix)) + np.multiply(s_matrix, norm.pdf(Z_matrix))
        y = np.min(np.sqrt(np.sum(EI_matrix**2,axis=1)),axis=0).reshape(-1,1)

        return y

    def EIMoptimiserWrapper(self, Xcont, Xqual, constraints=False, mode='euclidean'):

        X = np.concatenate((Xcont.reshape((1,-1)), Xqual.reshape((1,-1))), axis=1)

        if constraints is not False:
            return -self.CEIM_Hypervolume(X)

        return -self.EIM(X,mode).reshape(-1)

    def AEIMoptimiserWrapper(self, Xcont, Xqual, constraints=False):

        X = np.concatenate((Xcont.reshape((1,-1)), Xqual.reshape((1,-1))), axis=1)

        return -self.AEIM_Euclidean(X).reshape(-1)
        
            

    def EIMmixedoptimiser(self, constraints, algorithm='Random Local', values=None, mode='euclidean'):
        """
        Optimise EI search whole domain
        """
        if algorithm == 'Random':
            Xsamples = self.sample_design(samples=10000, design='halton')

            if constraints is False:
                fvals = self.EIM(Xsamples, mode=mode)
            else:
                fvals = self.CEIM_Hypervolume(Xsamples)

            fmax = np.amax(fvals)
            indymax = np.argmax(fvals)
            xmax = Xsamples[indymax,:]
            if values is None:
                return fmax, xmax
            return fmax, xmax, fvals, Xsamples
        elif algorithm == 'Random Local':
            Xsamples = self.sample_design(samples=10000, design='halton')

            if constraints is False:
                fvals = self.EIM(Xsamples, mode=mode)
            else:
                fvals = self.CEIM_Hypervolume(Xsamples)
            if mode == 'all':
                fmax = np.max(fvals,axis=0)
                print(fvals.shape)
                print(fmax.shape)
                indmax = np.argmax(fvals,axis=0)
                print(indmax)
                xmax = Xsamples[indmax,:]
                qual = xmax[:,-self.num_qual:].reshape(-1)

                bnd = list(self.bounds[:,:self.num_quant].T)
                bndlist = []

                for element in bnd:
                    bndlist.append(tuple(element))

                modes = ['euclidean', 'hypervolume']
                results = []
                for i in range(2):
                    results.append(stats.optimize.minimize(self.EIMoptimiserWrapper, xmax[i,:-self.num_qual].reshape(-1), args=(qual[i],constraints,modes[i]), bounds=bndlist,method='SLSQP'))

                xmax = np.concatenate((results[0].x, qual[0]),axis=None)
                xmax = np.vstack((xmax,np.concatenate((results[1].x, qual[1]),axis=None)))

                fmax = np.array((results[0].fun,results[1].fun))

                return fmax, xmax

            fmax = np.amax(fvals)
            indymax = np.argmax(fvals)
            xmax = Xsamples[indymax,:]
            qual = xmax[self.num_quant:]

            bnd = list(self.bounds[:,:self.num_quant].T)
            bndlist = []

            for element in bnd:
                bndlist.append(tuple(element))

            result = stats.optimize.minimize(self.EIMoptimiserWrapper, xmax[:self.num_quant].reshape(-1), args=(qual,constraints,mode), bounds=bndlist,method='SLSQP')
            if values is None:
                
                return result.fun, np.concatenate((result.x, qual),axis=None)

            return fmax, xmax, fvals, Xsamples

        else:
            raise NotImplementedError()
             

    
    def AEIMmixedoptimiser(self, constraints, algorithm='Random', values=None):

        # Get estimate for mean variance of model using halton sampling
        X = self.sample_design(samples=10000, design='halton')
        X = self.scaleX(X, mode='bounds')
        varlist = []
        for iobj in range(self.num_obj):
            _ , var = self.models[iobj].predict_y(X)
            varlist.append(var)

        var = np.concatenate(varlist, axis=1)
        meanvar = np.mean(var,axis=0)

        f = self.currentfront

        self.contextual = np.divide(meanvar, f)


        # Optimise acquisition

        if algorithm == 'Random':

            Xsamples = self.sample_design(samples=10000, design='halton')

            fvals = self.AEIM_Hypervolume(Xsamples)

            fmax = np.amax(fvals)
            indymax = np.argmax(fvals)
            xmax = Xsamples[indymax,:]
            if values is None:
                return fmax, xmax
            return fmax, xmax, fvals, Xsamples

        elif algorithm == 'Random Local':
            Xsamples = self.sample_design(samples=10000, design='halton')

            if constraints is False:
                fvals = self.AEIM_Euclidean(Xsamples)
            else:
                raise NotImplementedError()

            fmax = np.amax(fvals)
            indymax = np.argmax(fvals)
            xmax = Xsamples[indymax,:]
            qual = xmax[-self.num_qual:]

            bnd = list(self.bounds[:,:self.num_quant].T)
            bndlist = []

            for element in bnd:
                bndlist.append(tuple(element))

            result = stats.optimize.minimize(self.AEIMoptimiserWrapper, xmax[:-self.num_qual].reshape(-1), args=(qual,constraints), bounds=bndlist,method='SLSQP')
            if values is None:
                
                return result.fun, np.concatenate((result.x, qual),axis=None)

            return fmax, xmax, fvals, Xsamples

        elif algorithm == 'SHGO':
            if self.num_qual < 1:
                bnd = list(self.bounds.T)
                bndlist = []

                for element in bnd:
                    bndlist.append(tuple(element))
            
                result = shgo(self.AEIM_Hypervolume,bndlist, sampling_method='sobol', n=30, iters=2)
                
                return result.x, result.fun
            else:
                sample = self.sample_design(samples=1, design='random')
                contbnd = list(self.bounds[:,:self.num_quant].T)
                contbndlist = []
                qual = sample[:,-self.num_qual:]

                for element in contbnd:
                    contbndlist.append(tuple(element))
                resXstore = []
                resFstore = []
                for i in range(np.shape(qual)[0]):
                    result = shgo(self.AEIMoptimiserWrapper, contbndlist, args=(qual[i,:]), sampling_method='sobol', n=30, iters=2)
                    resXstore.append(result.x)
                    resFstore.append(result.fun)

                # sort for each discrete combination and get best point
                ind = resFstore.index(min(resFstore))  
                xmax = np.concatenate((resXstore[ind],qual[ind,:]))
                fval = min(resFstore)      
                return fval, xmax

        elif algorithm == 'DE':
            if self.num_qual < 1:
                bnd = list(self.bounds.T)
                bndlist = []

                for element in bnd:
                    bndlist.append(tuple(element))
            
                result = differential_evolution(self.AEIM_Hypervolume,bndlist)
                
                return result.x, result.fun
            else:
                sample = self.sample_design(samples=1, design='random')
                contbnd = list(self.bounds[:,:self.num_quant].T)
                contbndlist = []
                qual = sample[:,-self.num_qual:]

                for element in contbnd:
                    contbndlist.append(tuple(element))
                resXstore = []
                resFstore = []
                for i in range(np.shape(qual)[0]):
                    result = dual_annealing(self.AEIMoptimiserWrapper, contbndlist, args=(qual[i,:]))
                    resXstore.append(result.x)
                    resFstore.append(result.fun)

                # sort for each discrete combination and get best point
                ind = resFstore.index(min(resFstore))  
                xmax = np.concatenate((resXstore[ind],qual[ind,:]))
                fval = min(resFstore)      
                return fval, xmax
        

        return      

    def multinextcondition(self, X, Y, constraints=False, values=None, method='EIM', mode='euclidean'):
        """
        Suggest the next condition for evaluation
        """
        if constraints is False:
            try:
                self.k_type = 'matern3'
                self.models = self.generatemodels(X, Y)
            except:
                print('Initial model optimisation failed, retrying with new kernel')
                try:
                    self.k_type = 'matern5'
                    self.models = self.generatemodels(X, Y)
                except:
                    print('Model optimisation failed, retrying with new value of variance')
                    for variance in [0.1,1,2,10]:
                        try:
                            self.models = self.generatemodels(X, Y, variance=variance)
                        except:
                            print('Model optimisation failed, retrying with new value of variance')

            self.currentfront = self.paretofront(self.Yscaled)

            means = []
            for model in self.models:
                mean, _ = model.predict_y(self.sample_design(samples=2, design='halton'))
                means.append(mean.numpy())
            if np.any(means == np.nan):
                print("Retraining model with new starting variance")
                self.models = self.generatemodels(X, Y, variance=0.1)

            if method == 'AEIM':
                fmax, xmax = self.AEIMmixedoptimiser(constraints, algorithm='Random Local')
            else:
                fmax, xmax = self.EIMmixedoptimiser(constraints, algorithm='Random Local',mode=mode)
            
            if values is None and mode != 'all':
                return xmax.reshape(1,-1), fmax
            elif values is None and mode == 'all':
                if np.allclose(xmax[0,:],xmax[1,:], rtol=1e-3, atol=1e-5):
                    return xmax[0,:].reshape(1,-1), fmax[0]             
                return np.unique(xmax.round(6),axis=0), fmax
 
        self.models = self.generatemodels(X,Y)
        self.currentfront = self.paretofront(self.Yscaled)
        self.constrainedmodels = self.generatemodels(X, constraints, scale=False)

        fmax, xmax = self.EIMmixedoptimiser(constraints, algorithm='Simplical')
        if values is None:
            return xmax.reshape(1,-1), fmax