from __future__ import division # No automatic floor division
from base import *
from scipy.sparse import dia_matrix, csr_matrix, spdiags
from scipy.sparse.linalg import spsolve

class F1D(Flexure):
  def initialize(self, filename):
    super(F1D, self).initialize(filename)
    if self.Verbose: print 'F1D initialized'

  def run(self):
    if self.method == 'FD':
      # Finite difference
      super(F1D, self).FD()
      self.method_func = self.FD
    elif self.method == 'FFT':
      # Fast Fourier transform
      super(F1D, self).FFT()
      self.method_func = self.FFT
    elif self.method == "SPA":
      # Superposition of analytical solutions
      super(F1D, self).SPA()
      self.method_func = self.SPA
    elif self.method == "SPA_NG":
      # Superposition of analytical solutions,
      # nonuniform points
      super(F1D, self).SPA_NG()
      self.method_func = self.SPA_NG
    else:
      sys.exit('Error: method must be "FD", "FFT", or "SPA"')

    if self.Verbose: print 'F1D run'
    self.method_func ()
    # self.plot() # in here temporarily

  def finalize(self):
    if self.Verbose: print 'F1D finalized'
    super(F1D, self).finalize()   
    
  ########################################
  ## FUNCTIONS FOR EACH SOLUTION METHOD ##
  ########################################
  
  def FD(self):
    #try:
    #  self.plotChoice
    #except:
    #  self.plotChoice = None
    if self.plotChoice:
      self.gridded_x()
    # Only generate coefficient matrix if it is not already provided
    try:
      self.coeff
    except:
      self.elasprep() # define dx4 and D within self
      self.coeff_matrix_creator() # And define self.coeff
    self.direct_fd_solve() # Get the deflection, "w"

  def FFT(self):
    if self.plotChoice:
      self.gridded_x()
    sys.exit("The fast Fourier transform solution method is not yet implemented.")
    
  def SPA(self):
    self.gridded_x()
    self.spatialDomainVars()
    self.spatialDomainGridded()

  def SPA_NG(self):
    self.spatialDomainVars()
    self.spatialDomainNoGrid()

  
  ######################################
  ## FUNCTIONS TO SOLVE THE EQUATIONS ##
  ######################################


  ## UTILITY
  ############

  def gridded_x(self):
    self.nx = self.q0.shape[0]
    self.x = np.arange(0,self.dx*self.nx,self.dx)
    
  
  ## SPATIAL DOMAIN SUPERPOSITION OF ANALYTICAL SOLUTIONS
  #########################################################

  # SETUP

  def spatialDomainVars(self):
    self.D = self.E*self.Te**3/(12*(1-self.nu**2)) # Flexural rigidity
    self.alpha = (4*self.D/(self.drho*self.g))**.25 # 1D flexural parameter
    self.coeff = self.alpha**3/(8*self.D)

  # GRIDDED

  def spatialDomainGridded(self):
  
    self.w = np.zeros(self.nx) # Deflection array
    
    for i in range(self.nx):
      # Loop over locations that have loads, and sum
      if self.q0[i]:
        dist = abs(self.x[i]-self.x)
        # -= b/c pos load leads to neg (downward) deflection
        self.w -= self.q0[i] * self.coeff * self.dx * np.exp(-dist/self.alpha) * \
          (np.cos(dist/self.alpha) + np.sin(dist/self.alpha))
    # No need to return: w already belongs to "self"
    

  # NO GRID

  def spatialDomainNoGrid(self):
  
    # Reassign q0 for consistency
    #self.q0_with_locs = self.q0 # nah, will recombine later
    self.x = self.q0[:,0]
    self.q0 = self.q0[:,1]
    
    self.w = np.zeros(self.x.shape)
    if self.Debug:
      print "w = "
      print self.w.shape
    
    i=0 # counter
    for x0 in self.x:
      dist = abs(self.x-x0)
      self.w -= self.q0[i] * self.coeff * self.dx * np.exp(-dist/self.alpha) * \
        (np.cos(dist/self.alpha) + np.sin(dist/self.alpha))
      if i==10:
        if self.Debug:
          print dist
          print self.q0
      i+=1 # counter

  ## FINITE DIFFERENCE
  ######################
  
  def elasprep(self):
    """
    dx4, D = elasprep(dx,Te,E=1E11,nu=0.25)
    
    Defines the variables (except for the subset flexural rigidity) that are
    needed to run "coeff_matrix_1d"
    """
    self.dx4 = self.dx**4
    self.D = self.E*self.Te**3/(12*(1-self.nu**2))

  def coeff_matrix_creator(self):
    """
    coeff = coeff_matrix(D,drho,dx4,nu,g)
    where D is the flexural rigidity, nu is Poisson's ratio, drho is the  
    density difference between the mantle and the material filling the 
    depression, g is gravitational acceleration at Earth's surface (approx. 
    9.8 m/s), and dx4 is based on the distance between grid cells (dx).
    
    All grid parameters except nu and g are generated by the function
    varprep2d, located inside this module
    
    D must be one cell larger than q0, the load array.
  
    1D pentadiagonal matrix to solve 1D flexure with variable elastic 
    thickness via a Thomas algorithm (assuming that scipy uses a Thomas 
    algorithm).
    """
    
    self.coeff_start_time = time.time()
    
    ##########################
    # CONSTRUCT SPARSE ARRAY #
    ##########################

    self.build_diagonals()

    
    ########################################################
    # APPLY BOUNDARY CONDITIONS TO FLEXURAL RIGIDITY ARRAY #
    ########################################################

    self.BC_Rigidity()

    ##################################################
    # APPLY BOUNDARY CONDITIONS TO COEFFICIENT ARRAY #
    ##################################################

    # Some links that helped me teach myself how to set up the boundary conditions
    # in the matrix for the flexure problem:
    # 
    # Good explanation of and examples of boundary conditions
    # https://en.wikipedia.org/wiki/Euler%E2%80%93Bernoulli_beam_theory#Boundary_considerations
    # 
    # Copy of Fornberg table:
    # https://en.wikipedia.org/wiki/Finite_difference_coefficient
    # 
    # Implementing b.c.'s:
    # http://scicomp.stackexchange.com/questions/5355/writing-the-poisson-equation-finite-difference-matrix-with-neumann-boundary-cond
    # http://scicomp.stackexchange.com/questions/7175/trouble-implementing-neumann-boundary-conditions-because-the-ghost-points-cannot
    
    if self.Verbose:
      print "Boundary condition, West:", self.BC_W, type(self.BC_W)
      print "Boundary condition, East:", self.BC_E, type(self.BC_E)

    if self.BC_E == 'Dirichlet' or self.BC_W == 'Dirichlet':
      self.BC_Dirichlet()
    if self.BC_E == 'Sandbox' or self.BC_W == 'Sandbox':
      # Sandbox is the developer's testing ground
      sys.exit("Sandbox Closed")
    if self.BC_E == '0Moment0Shear' or self.BC_W == '0Moment0Shear':
      self.BC_0Moment0Shear()
    if self.BC_E == 'Neumann' or self.BC_W == 'Neumann':
      self.BC_Neumann()
    if self.BC_E == 'Mirror' or self.BC_W == 'Mirror':
      self.BC_Mirror()
    if self.BC_E == '0Slope0Shear' or self.BC_W == '0Slope0Shear':
      self.BC_0Slope0Shear()

    ##########################################################
    # INCORPORATE BOUNDARY CONDITIONS INTO COEFFICIENT ARRAY #
    ##########################################################

    # Roll to keep the proper coefficients at the proper places in the
    # arrays: Python will naturally just do vertical shifts instead of 
    # diagonal shifts, so this takes into account the horizontal compoent 
    # to ensure that boundary values are at the right place.
    self.l2_orig = self.l2.copy()
    self.l2 = np.roll(self.l2, -2)
    self.l1 = np.roll(self.l1, -1)
    self.r1 = np.roll(self.r1, 1)
    self.r2 = np.roll(self.r2, 2)
    # Then assemble these rows: this is where the periodic boundary condition 
    # can matter.
    if self.BC_E == 'Periodic' or self.BC_W == 'Periodic':
      self.BC_Periodic()
    # If not periodic, standard assembly (see BC_Periodic fcn for the assembly 
    # of that set of coefficient rows
    else:
      self.diags = np.vstack((self.l2,self.l1,self.c0,self.r1,self.r2))
      self.offsets = np.array([-2,-1,0,1,2])

    # Everybody now (including periodic b.c. cases)
    self.coeff_matrix = spdiags(self.diags, self.offsets, self.nx, self.nx, format='csr')

    self.coeff_creation_time = time.time() - self.coeff_start_time
    # Always print this!
    print 'Time to construct coefficient (operator) array [s]:', self.coeff_creation_time
  
  def build_diagonals(self):
    """
    Builds the diagonals for the coefficient array
    """
    if np.isscalar(self.Te):
      # Diagonals, from left to right, for all but the boundaries 
      self.l2 = 1 * self.D/self.dx4
      self.l1 = -4 * self.D/self.dx4
      self.c0 = 6 * self.D/self.dx4 + self.drho*self.g
      self.r1 = -4 * self.D/self.dx4
      self.r2 = 1 * self.D/self.dx4
      # Make them into arrays
      self.l2 *= np.ones(self.q0.shape)
      self.l1 *= np.ones(self.q0.shape)
      self.c0 *= np.ones(self.q0.shape)
      self.r1 *= np.ones(self.q0.shape)
      self.r2 *= np.ones(self.q0.shape)
    elif type(self.Te) == np.ndarray:
      # l2 corresponds to top value in solution vector, so to the left (-) side
      # Good reference for how to determine central difference (and other) coefficients is:
      # Fornberg, 1998: Generation of Finite Difference Formulas on Arbitrarily Spaced Grids
      Dm1 = self.D[:-2]
      D0  = self.D[1:-1]
      Dp1 = self.D[2:]
      self.l2 = ( Dm1/2. + D0 - Dp1/2. ) / self.dx4
      self.l1 = ( -6.*D0 + 2.*Dp1 ) / self.dx4
      self.c0 = ( -2.*Dm1 + 10.*D0 - 2.*Dp1 ) / self.dx4 + self.drho*self.g
      self.r1 = ( 2.*Dm1 - 6.*D0 ) / self.dx4
      self.r2 = ( -Dm1/2. + D0 + Dp1/2. ) / self.dx4
    # Number of columns; equals number of rows too - square coeff matrix
    self.ncolsx = self.c0.shape[0]
    
    # Either way, the way that Scipy stacks is not the same way that I calculate
    # the rows. It runs offsets down the column instead of across the row. So
    # to simulate this, I need to re-zero everything. To do so, I use 
    # numpy.roll.

  def BC_Rigidity(self):
    """
    Utility function to help implement boundary conditions by specifying 
    them for and applying them to the elastic thickness grid
    """

    if np.isscalar(self.Te):
      if self.Debug:
        print("Scalar Te: no need to modify boundaries.")
    else:

      ##############################################################
      # AUTOMATICALLY SELECT FLEXURAL RIGIDITY BOUNDARY CONDITIONS #
      ##############################################################
      # West
      if self.BC_W == 'Periodic':
        self.BC_Rigidity_W = 'periodic'
      elif (self.BC_W == np.array(['Dirichlet0', '0Moment0Shear', '0Slope0Shear'])).any():
        self.BC_Rigidity_W = '0 curvature'
      elif self.BC_W == 'Mirror':
        self.BC_Rigidity_W = 'mirror symmetry'
      else:
        sys.exit("Invalid Te B.C. case")
      # East
      if self.BC_E == 'Periodic':
        self.BC_Rigidity_E = 'periodic'
      elif (self.BC_E == np.array(['Dirichlet0', '0Moment0Shear', '0Slope0Shear'])).any():
        self.BC_Rigidity_E = '0 curvature'
      elif self.BC_E == 'Mirror':
        self.BC_Rigidity_E = 'mirror symmetry'
      else:
        sys.exit("Invalid Te B.C. case")
      
      #############
      # PAD ARRAY #
      #############
      # self.D = np.hstack([np.nan, self.D, np.nan])
      # Temporarily:
      self.D[0] = np.nan
      self.D[-1] = np.nan

      ###############################################################
      # APPLY FLEXURAL RIGIDITY BOUNDARY CONDITIONS TO PADDED ARRAY #
      ###############################################################
      if self.BC_Rigidity_W == "0 curvature":
        self.D[0] = 2*self.D[1] - self.D[2]
      if self.BC_Rigidity_E == "0 curvature":
        self.D[-1] = 2*D[-2] - D[-3]
      if self.BC_Rigidity_W == "mirror symmetry":
        self.D[0] = self.D[2]
      if self.BC_Rigidity_E == "mirror symmetry":
        self.D[-1] = self.D[-3]
      if self.BC_Rigidity_W == "periodic":
        self.D[0] = self.D[-2]
      if self.BC_Rigidity_E == "periodic":
        self.D[-1] = self.D[-3]

      ###################################################
      # DEFINE SUB-ARRAYS FOR DERIVATIVE DISCRETIZATION #
      ###################################################
      Dm1 = self.D[:-2]
      D0  = self.D[1:-1]
      Dp1 = self.D[2:]

      ###########################################################
      # DEFINE COEFFICIENTS TO W_-2 -- W_+2 WITH B.C.'S APPLIED #
      ###########################################################
      self.l2_coeff_i = ( Dm1/2. + D0 - Dp1/2. ) / self.dx4
      self.l1_coeff_i = ( -6.*D0 + 2.*Dp1 ) / self.dx4
      self.c0_coeff_i = ( -2.*Dm1 + 10.*D0 - 2.*Dp1 ) / self.dx4 + self.drho*self.g
      self.r1_coeff_i = ( 2.*Dm1 - 6.*D0 ) / self.dx4
      self.r2_coeff_i = ( -Dm1/2. + D0 + Dp1/2. ) / self.dx4
      
      """
      # Template For Coefficient Combination
      self.l2[i] = self.l2_coeff_i
      self.l1[i] = self.l1_coeff_i
      self.c0[i] = self.c0_coeff_i
      self.r1[i] = self.r1_coeff_i
      self.r2[i] = self.r2_coeff_i
      """
      
  def BC_Periodic(self):
    """
    Periodic boundary conditions: wraparound to the other side.
    """
    if self.BC_E == 'Periodic' and self.BC_W == 'Periodic':
      # If both boundaries are periodic, we are good to go (and self-consistent)
      pass # It is just a shift in the coeff. matrix creation.
    else:
      # If only one boundary is periodic and the other doesn't implicitly 
      # involve a periodic boundary, this is illegal!
      # I could allow it, but would have to rewrite the Periodic b.c. case,
      # which I don't want to do to allow something that doesn't make 
      # physical sense... so if anyone wants to do this for some unforeseen 
      # reason, they can just split my function into two pieces themselves.i
      sys.exit("Having the boundary opposite a periodic boundary condition\n"+
               "be fixed and not include an implicit periodic boundary\n"+
               "condition makes no physical sense.\n"+
               "Please fix the input boundary conditions. Aborting.")
    self.diags = np.vstack((self.r1,self.r2,self.l2,self.l1,self.c0,self.r1,self.r2,self.l2,self.l1))
    self.offsets = np.array([1-self.ncolsx,2-self.ncolsx,-2,-1,0,1,2,self.ncolsx-2,self.ncolsx-1])

  def BC_Dirichlet0(self):
    """
    Dirichlet boundary condition for 0 deflection.
    This requires that nothing be done to the edges of the solution array, 
    because the lack of the off-grid terms implies that they go to 0
    """
    if self.BC_W == 'Dirichlet0':
      pass
    if self.BC_E == 'Dirichlet0':
      pass

  def BC_0Slope0Shear(self):
    i=0
    """
    This boundary condition is esentially a Neumann 0-gradient boundary 
    condition with that 0-gradient state extended over a longer part of 
    the grid such that the third derivative also equals 0.
    
    This boundary condition has more of a geometric meaning than a physical 
    meaning. It produces a state in which the boundaries have to have all 
    gradients in deflection go to 0 (i.e. approach constant values) while 
    not specifying what those values must be.
    
    This uses a 0-curvature boundary condition for elastic thickness 
    that extends outside of the computational domain.
    """
    
    if np.isscalar(self.Te):
      if self.BC_W == '0Slope0Shear':
        i = 0
        self.l2[i] = np.nan # OFF GRID: using np.nan to throw a clear error if this is included
        self.l1[i] = np.nan # OFF GRID
        self.c0[i] = 6 * self.D/self.dx4 + self.drho*self.g
        self.r1[i] = -8 * self.D/self.dx4
        self.r2[i] = 2 * self.D/self.dx4
        i = 1
        self.l2[i] = np.nan # OFF GRID
        self.l1[i] = -4 * self.D/self.dx4
        self.c0[i] = 6 * self.D/self.dx4 + self.drho*self.g
        self.r1[i] = -4 * self.D/self.dx4
        self.r2[i] = 2 * self.D/self.dx4
      if self.BC_E == '0Slope0Shear':
        i = -2
        self.l2[i] = 2 * self.D/self.dx4
        self.l1[i] = -4 * self.D/self.dx4
        self.c0[i] = 6 * self.D/self.dx4 + self.drho*self.g
        self.r1[i] = -4 * self.D/self.dx4
        self.r2[i] = np.nan # OFF GRID
        i = -1
        self.l2[i] = 2 * self.D/self.dx4
        self.l1[i] = -8 * self.D/self.dx4
        self.c0[i] = 6 * self.D/self.dx4 + self.drho*self.g
        self.r1[i] = np.nan # OFF GRID
        self.r2[i] = np.nan # OFF GRID
    else:
      # More general solution for variable Te: makes above solution 
      # redundant with this. See comment in 0Moment0Shear for more 
      # thoughts on this.
      if self.BC_W == '0Slope0Shear':
        i=0
        self.l2[i] = np.nan
        self.l1[i] = np.nan
        self.c0[i] = self.c0_coeff_i
        self.r1[i] = self.r1_coeff_i + self.l1_coeff_i
        self.r2[i] = self.r2_coeff_i + self.l2_coeff_i
        i=1
        self.l2[i] = np.nan
        self.l1[i] = self.l1_coeff_i
        self.c0[i] = self.c0_coeff_i
        self.r1[i] = self.r1_coeff_i
        self.r2[i] = self.r2_coeff_i + self.l2_coeff_i
      if self.BC_E == '0Slope0Shear':
        i=-2
        self.l2[i] = self.l2_coeff_i + self.r2_coeff_i
        self.l1[i] = self.l1_coeff_i
        self.c0[i] = self.c0_coeff_i
        self.r1[i] = self.r1_coeff_i
        self.r2[i] = np.nan
        i=-1
        self.l2[i] = self.l2_coeff_i + self.r2_coeff_i
        self.l1[i] = self.l1_coeff_i + self.r1_coeff_i
        self.c0[i] = self.c0_coeff_i
        self.r1[i] = np.nan
        self.r2[i] = np.nan

  def BC_0Moment0Shear(self):
    """
    d2w/dx2 = d3w/dx3 = 0
    (no moment or shear)
    This simulates a free end (broken plate, end of a cantilevered beam: 
    think diving board tip)
    It is *not* yet set up to have loads placed on the ends themselves: 
    (look up how to do this, thought Wikipdia has some info, but can't find
    it... what I read said something about generalizing)
    """
    # 0 moment and 0 shear
    if np.isscalar(self.Te):
    
      #self.q0[:] = np.max(self.q0)
    
      # SET BOUNDARY CONDITION ON WEST (LEFT) SIDE
      if self.BC_W == '0Moment0Shear':
        i=0
        """
        # This is for a Neumann b.c. combined with third deriv. = 0
        self.l2[i] = np.nan # OFF GRID: using np.nan to throw a clear error if this is included
        self.l1[i] = np.nan # OFF GRID
        self.c0[i] = 6 * self.D/self.dx4 + self.drho*self.g # this works but not sure how to get it.
                                                            # OH, you can w/ 0-flux boundary
                                                            # And 10 with 0-moment boundary
                                                            # But that doesn't make sense with pics.
                                                            # 0 moment should als be free deflec.
        self.r1[i] = -8 * self.D/self.dx4
        self.r2[i] = 2 * self.D/self.dx4
        """
        self.l2[i] = np.nan # OFF GRID: using np.nan to throw a clear error if this is included
        self.l1[i] = np.nan # OFF GRID
        self.c0[i] = 2 * self.D/self.dx4 + self.drho*self.g
        self.r1[i] = -4 * self.D/self.dx4
        self.r2[i] = 2 * self.D/self.dx4
        i=1
        self.l2[i] = np.nan # OFF GRID
        self.l1[i] = -2 * self.D/self.dx4
        self.c0[i] = 6 * self.D/self.dx4 + self.drho*self.g
        self.r1[i] = -6 * self.D/self.dx4
        self.r2[i] = 2 * self.D/self.dx4
        
      # SET BOUNDARY CONDITION ON EAST (RIGHT) SIDE
      if self.BC_E == '0Moment0Shear':
        # Here, directly calculated new coefficients instead of just adding
        # them in like I did to save some time (for me) in the variable Te
        # case, below.
        i=-1
        self.r2[i] = np.nan # OFF GRID: using np.nan to throw a clear error if this is included
        self.r1[i] = np.nan # OFF GRID
        self.c0[i] = 6 * self.D/self.dx4 + self.drho*self.g
        self.l1[i] = -8 * self.D/self.dx4
        self.l2[i] = 2 * self.D/self.dx4
        i=-2
        self.r2[i] = np.nan # OFF GRID
        self.r1[i] = -4 * self.D/self.dx4
        self.c0[i] = 6 * self.D/self.dx4 + self.drho*self.g
        self.l1[i] = -4 * self.D/self.dx4
        self.l2[i] = 2 * self.D/self.dx4
        """
        self.r2[i] = np.nan # OFF GRID
        self.r1[i] = -4 * self.D/self.dx4
        self.c0[i] = 6 * self.D/self.dx4 + self.drho*self.g
        self.l1[i] = -4 * self.D/self.dx4
        self.l2[i] = 2 * self.D/self.dx4
        """
    else:
      # Variable Te
      # But this is really the more general solution, so we don't need the 
      # constant Te case... but I just keep it because I already wrote it
      # and it probably calculates the solution negligibly faster.
      # 
      # First, just define coefficients for each of the positions in the array
      # These will be added in code instead of being directly combined by 
      # the programmer (as I did above for constant Te), which might add 
      # rather negligibly to the compute time but save a bunch of possibility 
      # for unfortunate typos!

      # Also using 0-curvature boundary condition for D (i.e. Te)
      if self.BC_W == '0Moment0Shear':
        i=0
        self.l2[i] = np.nan
        self.l1[i] = np.nan
        self.c0[i] = self.c0_coeff_i + 4*self.l2_coeff_i + 2*self.l1_coeff_i
        self.r1[i] = self.r1_coeff_i - 4*self.l2_coeff_i - self.l1_coeff_i
        self.r2[i] = self.r2_coeff_i + self.l2_coeff_i
        i=1
        self.l2[i] = np.nan
        self.l1[i] = self.l1_coeff_i + 2*self.l2_coeff_i
        self.c0[i] = self.c0_coeff_i
        self.r1[i] = self.r1_coeff_i - 2*self.l2_coeff_i
        self.r2[i] = self.r2_coeff_i + self.l2_coeff_i
      
      if self.BC_E == '0Moment0Shear':
        i=-2
        self.l2[i] = self.l2_coeff_i + self.r2_coeff_i
        self.l1[i] = self.l1_coeff_i - 2*self.r2_coeff_i
        self.c0[i] = self.c0_coeff_i
        self.r1[i] = self.r1_coeff_i + 2*self.r2_coeff_i
        self.r2[i] = np.nan
        i=-1
        self.l2[i] = self.l2_coeff_i + self.r2_coeff_i
        self.l1[i] = self.l1_coeff_i - 4*self.r2_coeff_i - self.r1_coeff_i
        self.c0[i] = self.c0_coeff_i + 4*self.r2_coeff_i + 2*self.r1_coeff_i
        self.r1[i] = np.nan
        self.r2[i] = np.nan

  def BC_Mirror(self):
    """
    Mirrors q0 across the boundary on either the west (left) or east (right) 
    side, depending on the selections.
    
    This can, for example, produce a scenario in which you are observing 
    a mountain range up to the range crest (or, more correctly, the halfway 
    point across the mountain range).
    """
    if self.BC_W == 'Mirror':
      i=0
      self.l2[i] = np.nan
      self.l1[i] = np.nan
      self.c0[i] = self.c0_coeff_i
      self.r1[i] = self.r1_coeff_i + self.l1_coeff_i
      self.r2[i] = self.r2_coeff_i + self.l2_coeff_i
      i=1
      self.l2[i] = np.nan
      self.l1[i] = self.l1_coeff_i
      self.c0[i] = self.c0_coeff_i + self.l2_coeff_i
      self.r1[i] = self.r1_coeff_i
      self.r2[i] = self.r2_coeff_i
    
    if self.BC_E == 'Mirror':
      i=-2
      self.l2[i] = self.l2_coeff_i
      self.l1[i] = self.l1_coeff_i
      self.c0[i] = self.c0_coeff_i + self.r2_coeff_i
      self.r1[i] = self.r1_coeff_i
      self.r2[i] = np.nan
      i=-1
      self.l2[i] = self.l2_coeff_i + self.r2_coeff_i
      self.l1[i] = self.l1_coeff_i + self.r1_coeff_i
      self.c0[i] = self.c0_coeff_i
      self.r1[i] = np.nan
      self.r2[i] = np.nan
    
  def calc_max_flexural_wavelength(self):
    """
    Returns the approximate maximum flexural wavelength
    This is important when padding of the grid is required: in Flexure (this 
    code), grids are padded out to one maximum flexural wavelength, but in any 
    case, the flexural wavelength is a good characteristic distance for any 
    truncation limit
    """
    if np.isscalar(self.D):
      Dmax = self.D
    else:
      Dmax = self.D.max()
    # This is an approximation if there is fill that evolves with iterations 
    # (e.g., water), but should be good enough that this won't do much to it
    alpha = (4*Dmax/(self.drho*self.g))**.25 # 2D flexural parameter
    self.maxFlexuralWavelength = 2*np.pi*alpha
    self.maxFlexuralWavelength_ncells = int(np.ceil(self.maxFlexuralWavelength / self.dx))
    
  def direct_fd_solve(self):
    """
    w = direct_fd_solve()
      where coeff is the sparse coefficient matrix output from function
      coeff_matrix and q0 is the array of loads

    Sparse solver for one-dimensional flexure of an elastic plate
    """
    
    if self.Debug:
      print 'q0', self.q0.shape
      print 'Te', self.Te.shape
      self.calc_max_flexural_wavelength()
      print 'maxFlexuralWavelength_ncells', self.maxFlexuralWavelength_ncells
    
    self.solver_start_time = time.time()
    
    self.q0sparse = csr_matrix(-self.q0) # Negative so bending down with positive load,
                                    # bending up with negative load (i.e. material
                                    # removed)
                                    # *self.dx
    # UMFpack is now the default, but setting true just to be sure in case
    # anything changes
    self.w = spsolve(self.coeff_matrix, self.q0sparse, use_umfpack=True)
    
    self.time_to_solve = time.time() - self.solver_start_time
    # Always print this!
    print 'Time to solve [s]:', self.time_to_solve

    if self.Debug:
      print "w.shape:"
      print self.w.shape
      print "w:"
      print self.w
    
