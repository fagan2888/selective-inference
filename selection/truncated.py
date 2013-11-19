"""
This module implements the class `truncated_gaussian` which 
performs (conditional) UMPU tests for Gaussians
restricted to a set of intervals.

"""
import numpy as np
from selection.intervals import _CDF
from scipy.stats import norm as ndist
from mpmath import mp
mp.dps = 60
import rpy2.robjects as rpy

def _cdf(a,b):
    return np.array(_CDF(a,b))

def _dnorm(x):
    return np.array(mp.npdf(x))

def _qnorm(q):
    return np.array(mp.erfinv(2*q-1)*mp.sqrt(2))

class truncated_gaussian(object):
    
    """
    A Gaussian distribution, truncated to
    """

    def __init__(self, intervals, mu=0, sigma=1):
        intervals = np.asarray(intervals).reshape(-1)
        self._cutoff_array = np.sort(intervals)
        D = self.intervals[:,1]-self.intervals[:,0]
        I = self.intervals[D != 0]
        self._cutoff_array = I.reshape(-1)
        self._mu = mu
        self._sigma = sigma
        self._mu_or_sigma_changed()

    def __array__(self):
        return self.intervals
    
    @property
    def intervals(self):
        return self._cutoff_array.reshape((-1,2))
    
    @property
    def negated(self):
        if not hasattr(self,"_negated"):
            self._negated = truncated_gaussian(np.asarray(-self._cutoff_array[::-1]),
                                               mu=self.mu,
                                               sigma=self.sigma)
        return self._negated
    
    # private method to update P and D after a change of parameters

    def _mu_or_sigma_changed(self):
        mu, sigma = self.mu, self.sigma
        self.P = np.array([_cdf((a-mu)/sigma, 
                                (b-mu)/sigma) for a, b in self.intervals])
        self.D = np.array([(_dnorm((a-mu)/sigma), _dnorm((b-mu)/sigma)) for a, b in self.intervals])

    # mean parameter : mu

    def set_mu(self, mu):
        self._mu = mu
        self._mu_or_sigma_changed()

    def get_mu(self):
        return self._mu

    mu = property(get_mu, set_mu)

    # variance parameter : sigma

    def set_sigma(self, sigma):
        self._sigma = sigma
        self._mu_or_sigma_changed()

    def get_sigma(self):
        return self._sigma

    sigma = property(get_sigma, set_sigma)

    @property
    def delta(self):
        """
        .. math::
 
            \begin{align}
              \delta_\mu(a,b) &\triangleq \int_a^b x\phi(x-\mu)\,dx \\
              &= - \phi(b-\mu) + \phi(a-\mu) +
              \mu\left(\Phi(b-\mu)-\Phi(a-\mu)\right),
            \end{align}

        """
        mu, P, D = self.mu, self.P, self.D
        return D[:,0] - D[:,1] + mu * P
    
    # End of properties

    @staticmethod
    def twosided(thresh, mu=0, sigma=1):
        thresh = np.fabs(thresh)
        return truncated_gaussian([(-np.inf,-thresh),(thresh,np.inf)],
                                  mu=mu, sigma=sigma)
    
    def __repr__(self):
        return '''%s(%s, mu=%0.3e, sigma=%0.3e)''' % (self.__class__.name,
                                                      self.intervals,
                                                      self.mu,
                                                      self.sigma)


    def find_interval(self, x):
        check = (x >= self.intervals[:,0]) * (x < self.intervals[:,1])
        k = np.nonzero(check)[0]
        if k.shape[0] > 1:
            raise ValueError('intervals are not disjoint: x is in %s' % `self.intervals[k]`)
        if k.shape == (0,):
            raise ValueError('x is not in the support')
        k = k[0]
        return k
    
    def CDF(self, x):
        P, mu = self.P, self.mu
        k = self.find_interval(x)
        return float(P[:k].sum() + _cdf(self.intervals[k,0] - mu, 
                                        x - mu)) / P.sum()
    
    def quantile(self, q):
        P, mu = self.P, self.mu
        Psum = P.sum()
        Csum = np.cumsum(np.array([0]+list(P)))
        k = max(np.nonzero(Csum < Psum*q)[0])
        pnorm_increment = Psum*q - Csum[k]
        if np.mean(self.intervals[k]) < 0:
            return mu + _qnorm(_cdf(-np.inf,self.intervals[k,0]-mu) + pnorm_increment)
        else:
            return mu - _qnorm(_cdf(self.intervals[k,0]-mu, np.inf) - pnorm_increment)
        
    # make a function for vector version?
    def right_endpoint(self, left_endpoint, alpha):
        c1 = left_endpoint # shorthand from Will's code
        mu, P = self.mu, self.P
        alpha1 = self.CDF(left_endpoint)
        if (alpha1 > alpha):
            return np.nan
        alpha2 = np.array(alpha - alpha1, np.float128)
        return self.quantile(mp.one-alpha2)
            
    def G(self, left_endpoint, alpha):
        """
        $g_{\mu}$ from Will's code
        """
        c1 = left_endpoint # shorthand from Will's code
        mu, P, D = self.mu, self.P, self.D

        const = np.array(1-alpha, np.float128)*(np.sum(D[:,0]-D[:,1]) + mu*P.sum())
        right_endpoint = self.right_endpoint(left_endpoint, alpha)
        valid_intervals = []
        for a, b in self.intervals:
            intersection = (max(left_endpoint, a),
                            min(right_endpoint, b))
            if intersection[1] > intersection[0]:
                valid_intervals.append(intersection)
        if valid_intervals:
            return truncated_gaussian(valid_intervals, mu=self.mu, sigma=self.sigma).delta.sum() - const
        else:
            return 0

    def dG(self, left_endpoint, alpha):
        """
        $gg_{\mu}$ from Will's code
        """
        c1 = left_endpoint # shorthand from Will's code
        D = self.D
        return (self.right_endpoint(left_endpoint, alpha) - 
                left_endpoint) * (_dnorm((left_endpoint - self.mu) / self.sigma))
    
def G(left_endpoints, mus, alpha, tg):
    """
    Compute the $G$ function of `tg(intervals)` over 
    `zip(left_endpoints, mus)`.

    A copy is made of `tg` and its $(\mu,\sigma)$ are not modified.
    """
    tg = truncated_gaussian(tg.intervals)
    results = []
    for left_endpoint, mu in zip(left_endpoints, mus):
        tg.mu = mu
        results.append(tg.G(left_endpoint, alpha))
    return np.array(results)

def dG(left_endpoints, mus, alpha, tg):
    """
    Compute the $G$ function of `tg(intervals)` over 
    `zip(left_endpoints, mus)`.

    A copy is made of `tg` and its $(\mu,\sigma)$ are not modified.
    """
    tg = truncated_gaussian(tg.intervals)
    results = []
    for left_endpoint, mu in zip(left_endpoints, mus):
        tg.mu = mu
        results.append(tg.dG(left_endpoint, alpha))
    return np.array(results)

def _UMAU(observed, alpha, tg, 
         mu_lo=None,
         mu_hi=None,
         tol=1.e-8):
    tg = truncated_gaussian(tg.intervals, sigma=tg.sigma)

    X = observed # shorthand
    if mu_lo is None:
        mu_lo = X
    if mu_hi is None:
        mu_hi = X + 2

    # find upper and lower points for bisection
    tg.mu = mu_lo
    while tg.G(X, alpha) < 0: # mu_too_high
        mu_lo, mu_hi = mu_lo - 2, mu_lo
        tg.mu = mu_lo

    tg.mu = mu_hi
    while tg.G(X, alpha) > 0: # mu_too_low
        mu_lo, mu_hi = mu_hi, mu_hi + 2
        tg.mu = mu_ho

    # bisection
    while mu_hi - mu_lo > tol:
        mu_bar = 0.5 * (mu_lo + mu_hi)
        tg.mu = mu_bar
        if tg.G(X, alpha) < 0:
            mu_hi = mu_bar
        else:
            mu_lo = mu_bar
    return mu_bar

