##############################################################################
# Institute for the Design of Advanced Energy Systems Process Systems
# Engineering Framework (IDAES PSE Framework) Copyright (c) 2018-2019, by the
# software owners: The Regents of the University of California, through
# Lawrence Berkeley National Laboratory,  National Technology & Engineering
# Solutions of Sandia, LLC, Carnegie Mellon University, West Virginia
# University Research Corporation, et al. All rights reserved.
#
# Please see the files COPYRIGHT.txt and LICENSE.txt for full copyright and
# license information, respectively. Both files are also available online
# at the URL "https://github.com/IDAES/idaes-pse".
##############################################################################
"""
Compression Model.

Reference:

Modekurti et al., (2017). "Design, Dynamic Modeling,
and Control of a Multistage CO2 Compresor System.
International Journal of Greenhouse Gas Control. v62. page 31-45

Created: April 2020
"""
__Author__ = "Quang Minh Le, John Eslick, Andrew Lee"

from enum import Enum
import pyomo.environ as pyo
from pyomo.environ import (
    NonNegativeReals,
    Var,
    value,
    log,
    sqrt,
    TransformationFactory,
    units as pyunits)
from pyomo.common.config import ConfigValue, In
from idaes.core import declare_process_block_class

from idaes.generic_models.unit_models.pressure_changer import CompressorData

import idaes.logger as idaeslog
from idaes.core.util.exceptions import ConfigurationError
from idaes.core.util.constants import Constants as const

_log = idaeslog.getLogger(__name__)


class ImpellerType(Enum):
    cover_impeller = 1
    open_impeller = 2
    custom = 3


class VaneDiffuserType(Enum):
    vane_diffuser = 1
    vaneless_diffuser = 2
    custom = 3


def _build_cover_impeller_equations(blk):
    @blk.Constraint(blk.flowsheet().config.time)
    def impeller_work_coeff_eqn(b, t):
        phi = blk.mass_flow_coeff[t]
        return b.impeller_work_coeff[t] * 100 * phi == (
                          0.62 * phi - phi * (phi / 0.4)**3 + 0.0014) * 100

    @blk.Constraint(blk.flowsheet().config.time)
    def polytropic_head_coeff_vaned_diffuser_eqn(b, t):
        phi = blk.mass_flow_coeff[t]
        return b.mu_p_v[t] * 100 * phi == (
                      0.51 * phi + phi**2 - 7.6 * phi**3 - 0.00025) * 100


def _build_open_impeller_equations(blk):
    @blk.Constraint(blk.flowsheet().config.time)
    def impeller_work_coeff_eqn(b, t):
        phi = blk.mass_flow_coeff[t]
        return b.impeller_work_coeff[t] * phi == (
                      0.68 * phi - phi * (phi / 0.37)**3 + 0.002)

    @blk.Constraint(blk.flowsheet().config.time)
    def polytropic_head_coeff_vaned_diffuser_eqn(b, t):
        phi = blk.mass_flow_coeff[t]
        return b.mu_p_v[t] * phi == 0.5 * (1 + (phi - 0.065) / abs(
            phi - 0.065)) * (
                0.59 * phi + 0.7 * phi**2 - 7.5 * phi**3 - 0.00025
                ) + 0.5 * (1 - (phi - 0.065) / abs(phi - 0.065)) * 0.6 * phi


def _build_vane_diffuser_equations(blk):
    @blk.Constraint(blk.flowsheet().config.time)
    def polytropic_head_coeff_eqn(b, t):
        return b.mu_p[t] == b.mu_p_v[t]

    @blk.Constraint(blk.flowsheet().config.time)
    def polytropic_efficiency_eqn(b, t):
        return b.eff_p[t] == b.eff_p_v[t]


def _build_vaneless_diffuser_equations(blk):
    @blk.Constraint(blk.flowsheet().config.time)
    def polytropic_head_coeff_eqn(b, t):
        return b.mu_p[t] == b.impeller_work_coeff[t] * b.eff_p[t]

    @blk.Constraint(blk.flowsheet().config.time)
    def polytropic_efficiency_eqn(b, t):
        phi = blk.mass_flow_coeff[t]
        return (b.eff_p[t] - b.eff_p_v[t]) * (
                      0.04 + 5 * phi + b.eff_p_v[t]**3) == -0.017


@declare_process_block_class("CompressionStage", doc="Compression Stage Model")
class CompressionStageData(CompressorData):
    # Pressure changer with isentropic compressor options
    CONFIG = CompressorData.CONFIG()
    CONFIG.declare(
        "impeller_type",
        ConfigValue(
            default=None,
            domain=In(ImpellerType),
            description="Impeller type, if custom provide an expression rule",
            doc="""The type of impeller, if custom provide an expression rule
with the impeller_rule argument.
**default** - ImpellerType.open_impeller
**Valid values** - {
ImpellerType.cover_impeller,
ImpellerType.open_impeller,
ImpellerType.custom}""",
        ),
    )
    CONFIG.declare(
        "vane_diffuser_type",
        ConfigValue(
            default=None,
            domain=In(VaneDiffuserType),
            description="Vane diffuser type,"
            "if custom provide an expression rule",
            doc="""The type of vane diffuser,"
            "if custom provide an expression rule
with the vane_diffuser_rule argument.
**default** - VaneDiffuserType.vane_diffuser
**Valid values** - {
VaneDiffuserType.vane_diffuser,
VaneDiffuserType.vaneless_diffuser,
VaneDiffuserType.custom}""",
        ),
    )
    CONFIG.declare(
        "impeller_callback",
        ConfigValue(
            default=None,
            description="This is a callback that adds an impeller.  The"
            "callback function takes the impeller block data argument.",
        ),
    )
    CONFIG.declare(
        "vane_diffuser_callback",
        ConfigValue(
            default=None,
            description="This is a callback that adds a vane diffuser."
            "The callback function takes the vane diffuser"
            "block data argument.",
        ),
    )

    def build(self):
        super().build()

        # add ports to compressor
        self.add_inlet_port(name="vapor_inlet", block=self.control_volume)
        self.add_outlet_port(name="vapor_outlet", block=self.control_volume)

        # Pyomo arc connect vapor inlet steam with control volume inlet
        TransformationFactory("network.expand_arcs").apply_to(self)

        #####################################################

        # Some shorter refernces to property blocks
        properties_in = self.control_volume.properties_in
        properties_out = self.control_volume.properties_out

        self.mass_flow_coeff = Var(self.flowsheet().config.time,
                                   initialize=0.0735,
                                   doc="Compressor Flow Coefficient",
                                   bounds=(0.01, 0.15))
        self.rspeed = Var(self.flowsheet().config.time,
                          initialize=74.1738,
                          doc='Rotation Speed of The Impeller',
                          bounds=(0.5, 8000),
                          units=1 / pyunits.s)
        self.U2 = Var(self.flowsheet().config.time,
                      initialize=315,
                      doc="Impeller Tip Speed",
                      bounds=(0, 500),
                      units=pyunits.m / pyunits.s)
        self.delta_enth_polytropic = Var(self.flowsheet().config.time,
                                         initialize=2548.5,
                                         doc="Polytropic Enthalpy Change",
                                         units=pyunits.J / pyunits.mol,
                                         within=NonNegativeReals)
        self.impeller_work_coeff = Var(self.flowsheet().config.time,
                                       initialize=0.6993,
                                       doc="Impeller Work Coefficient",
                                       bounds=(0.001, 1))
        self.mu_p_v = Var(self.flowsheet().config.time,
                          initialize=0.60,
                          doc="Polytropic Head Coefficient Vaned Diffuser",
                          bounds=(0.001, 1))
        self.mu_p = Var(self.flowsheet().config.time,
                        initialize=0.60,
                        doc="Polytropic Head Coefficient",
                        bounds=(0.001, 1))
        self.eff_p_v = Var(self.flowsheet().config.time,
                           initialize=0.85,
                           doc="Polytropic Efficiency Vaned Diffuser",
                           bounds=(0.001, 1))
        self.eff_p = Var(self.flowsheet().config.time,
                         initialize=0.85,
                         doc="Polytropic Efficiency",
                         bounds=(0.001, 1.0))
        self.Ma = Var(self.flowsheet().config.time,
                      initialize=0.1,
                      doc='Rotational Mach Number',
                      bounds=(0.5, 1.5))
        self.psi_3 = Var(self.flowsheet().config.time,
                         initialize=0.01,
                         doc="Dimensionless Exit Flow Coefficient",
                         within=NonNegativeReals,
                         units=pyunits.dimensionless)
        self.psi_s = Var(self.flowsheet().config.time,
                         initialize=0.01,
                         doc="Dimensionless Isentropic Head Coefficient",
                         within=NonNegativeReals,
                         units=pyunits.dimensionless)

        ########################################################
        # Declare variables for the model
        self.z_s = Var(initialize=0.97373,
                       doc="Compressibility factors at suction")
        self.z_d1 = Var(initialize=0.88949,
                        doc="variable used for calculating"
                        "compressibility factor at discharge pressure")
        self.efficiency_mech = Var(initialize=0.97,
                                   doc="Mechanical Efficiency")
        self.eff_drive = Var(initialize=1.0,
                             doc="Driver efficiency")
        self.r2 = Var(initialize=0.075,
                      doc="Impeller Tip Radius",
                      units=pyunits.m)

        ############################################################

        self.ratioP[:] = 2.0   # make sure these have a number value
        self.deltaP[:] = 0     # to avoid an error later in initialize

        ###########################################################
        # Calculate Mach number and tip impeller speed
        @self.Constraint(self.flowsheet().config.time, doc="Mach Number")
        def Ma_con(b, t):
            # assume single vapor phase.
            speed_of_sound = self.control_volume.properties_in[
                t].speed_sound_phase['Vap']
            return b.Ma[t] == b.U2[t] / speed_of_sound

        @self.Constraint(self.flowsheet().config.time, doc="Rotation Speed "
                         "of the Impeller")
        def rspeed_con(b, t):
            return b.U2[t] == 2 * const.pi * b.r2 * b.rspeed[t]

        # set up the vane diffuser rule.
        vdcb = self.config.vane_diffuser_callback
        vdselect = self.config.vane_diffuser_type
        if vdselect is not VaneDiffuserType.custom and vdcb is not None:
            _log.warning("A valve diffuser type is not custom.")
        elif vdselect == VaneDiffuserType.vane_diffuser:
            _build_vane_diffuser_equations(self)
        elif vdselect == VaneDiffuserType.vaneless_diffuser:
            _build_vaneless_diffuser_equations(self)
        else:
            if vdcb is None:
                raise ConfigurationError(
                    "No custom vane diffuser callback provided")
            vdcb(self)

        # set up the impeller rule.
        icb = self.config.impeller_callback
        iselect = self.config.impeller_type
        if iselect is not ImpellerType.custom and icb is not None:
            _log.warning("An impeller type is not custom.")
        elif iselect == ImpellerType.cover_impeller:
            _build_cover_impeller_equations(self)
        elif iselect == ImpellerType.open_impeller:
            _build_open_impeller_equations(self)
        else:
            if icb is None:
                raise ConfigurationError(
                    "No custom impeller callback provided")
            icb(self)

        # efficiency for vane diffuser
        @self.Constraint(self.flowsheet().config.time, doc="Polytropic "
                         "Efficiency")
        def eff_p_v_cons(b, t):
            return b.eff_p_v[t] * b.impeller_work_coeff[t] == b.mu_p_v[t]

        # Total enthalpy and entropy change through compressor stage
        # Isentropic enthalpy change (hisen - hin)
        @self.Expression(self.flowsheet().config.time, doc="Specific "
                         "Enthalpy Change of Isentropic Process")
        def delta_enth_isentropic(b, t):
            return b.properties_isentropic[t].enth_mol - \
                properties_in[t].enth_mol

        # Total enthalpy change (ho - hi)
        @self.Expression(self.flowsheet().config.time, doc="Actual Enthalpy "
                         "Change")
        def delta_enth_actual(b, t):
            return properties_out[t].enth_mol - properties_in[t].enth_mol

        # Entropy change
        @self.Expression(self.flowsheet().config.time, doc="Entropy change in"
                         "Compressor Stage")
        def deltaS(b, t):
            return properties_out[t].entr_mol - properties_in[t].entr_mol

        @self.Constraint(self.flowsheet().config.time, doc="Polytropic "
                         "Enthalpy Correlation")
        def polytropic_correlation(b, t):
            return b.delta_enth_polytropic[t] == b.mu_p[t] * \
                b.delta_enth_actual[t] / b.impeller_work_coeff[t]

        # Correlation between actual enthalpy and polytropic enthalpy
        # This equation is obtained by Eq. (2.13) from Aungier textbook (2000)
        @self.Constraint(self.flowsheet().config.time, doc="Equation for"
                         "Polytropic Enthalpy")
        def delta_enth_polytropic_con(b, t):
            Tout = properties_out[t].temperature
            Tin = properties_in[t].temperature
            return b.delta_enth_polytropic[t] == b.delta_enth_actual[t] \
                - b.deltaS[t] * (Tout - Tin)/log(Tout / Tin)

        # Maximum impeller speed for individual stage
        @self.Expression(
            self.flowsheet().config.time,
            doc="Maximum Allowable Impeller Tip Speed")
        def U2max(b, t):
            phi = b.mass_flow_coeff[t]
            return sqrt((1984.1 * phi**2 - 616.88 * phi + 215.97) * 0.7 * 830)

        # Thermodynamic power
        @self.Expression(self.flowsheet().config.time,
                         doc="Thermodynamic Power")
        def fluid_pow(b, t):
            flow = properties_in[t].flow_mol
            return b.delta_enth_actual[t] * flow

        # Electricity power
        @self.Expression(self.flowsheet().config.time, doc="Shaft Power")
        def elec_pow(b, t):
            return b.fluid_pow[t] / (b.efficiency_mech * b.eff_drive)

        # -------------------------------------------------------------------
        # Static Volumetric Flow at Suction Inlet
        @self.Expression(self.flowsheet().config.time,
                         doc="Static Volumetric Flow at Suction Inlet")
        def Vsdot(b, t):
            flow_in = properties_in[t].flow_mol
            rho_v0 = properties_in[t].dens_mol
            return flow_in / rho_v0

        # Mass flow coefficient
        @self.Constraint(
            self.flowsheet().config.time, doc="Mass Flow Coefficient")
        def mass_flow_coeff_eqn(b, t):
            phi = b.mass_flow_coeff[t]
            return phi == b.Vsdot[t] / (const.pi * b.r2**2 * b.U2[t])

        # Static volumetric flow at impeller exit
        @self.Expression(self.flowsheet().config.time,
                         doc="Static volumetric flow at impeller exit")
        def V3dot(b, t):
            Tin = properties_in[t].temperature
            Tout = properties_out[t].temperature
            Pd = self.vapor_outlet.pressure[t]
            Ps = self.vapor_inlet.pressure[t]
            b.z_d = 0.5 * (b.z_s + b.z_d1)
            return b.Vsdot[t] * (b.z_d / b.z_s) * (Tout / Tin) * (Ps / Pd)

        # Dimensionless Exit Flow Coefficient (Performance Curve)
        @self.Constraint(self.flowsheet().config.time,
                         doc="Dimensionless Exit Flow Coefficient")
        def psi_3_eqn(b, t):
            b2 = 0.076 * 2 * b.r2
            return b.psi_3[t] == b.V3dot[t] / (
                const.pi * 2 * b.r2 * b2 * b.U2[t])

        # Isentropic head
        @self.Expression(self.flowsheet().config.time,
                         doc="Isentropic Head")
        def ys_model(b, t):
            k_v = self.control_volume.properties_in[t].heat_capacity_ratio
            a = (k_v - 1) / k_v
            Pd = self.vapor_outlet.pressure[t]
            Ps = self.vapor_inlet.pressure[t]
            Tin = properties_in[t].temperature
            mw = properties_in[t].mw
            gas_const = const.gas_constant
            return b.z_s * (gas_const / mw) * Tin * (1 / a) * ((Pd/Ps)**a - 1)

        # Dimensionless Isentropic Head Coefficient (Performance Curve)
        @self.Constraint(self.flowsheet().config.time,
                         doc="Dimensionless Isentropic Head Coefficient")
        def psi_s_eqn(b, t):
            return b.psi_s[t] == 2 * b.ys_model[t] / (b.U2[t]**2)

    def initialize(self, state_args={}, outlvl=idaeslog.NOTSET, solver='ipopt',
                   optarg={'tol': 1e-6, 'max_iter': 50}):
        """
        Initialize the inlet compressor stage model.
        This deactivates the specialized constraints,
        then does the isentropic compressor initialization,
        then reactivates the constraints and solves.

        Args:
            state_args (dict): Initial state for property initialization
            outlvl: Initialization logger level
            solver (str): Solver to use for initialization
            optarg (dict): Solver arguments dictionary
        """
        init_log = idaeslog.getInitLogger(self.name, outlvl, tag="unit")
        solve_log = idaeslog.getSolveLogger(self.name, outlvl, tag="unit")

        opt = pyo.SolverFactory(solver)
        opt.options = optarg

        unfix_ratioP = {}
        for t in self.flowsheet().config.time:
            # if there is not a good guess for efficiency or outlet pressure
            # provide something reasonable.
            eff = self.efficiency_isentropic[t]
            eff.fix(
                eff.value if pyo.value(eff) > 0.3 and pyo.value(
                    eff) < 1.0 else 0.85)
            # check for alternate pressure specs
            if self.outlet.pressure[t].fixed:
                self.ratioP[t] = pyo.value(
                    self.outlet.pressure[t] / self.inlet.pressure[t])
            elif self.control_volume.deltaP[t].fixed:
                self.ratioP[t] = pyo.value(
                    (self.control_volume.deltaP[t] + self.inlet.pressure[t]
                     ) / self.inlet.pressure[t])
            elif self.ratioP[t].fixed:
                self.outlet.pressure[t] = pyo.value(
                    self.ratioP[t] * self.inlet.pressure[t])
            else:
                if value(self.ratioP[t]) is None or value(
                        self.ratioP[t]) < 1.01:
                    self.ratioP[t].fix(1.5)
                else:
                    self.ratioP[t].fix()
                unfix_ratioP[t] = True

        # set list of constraints
        constraint_list = [
            "impeller_work_coeff_eqn",
            "polytropic_head_coeff_vaned_diffuser_eqn",
            "polytropic_head_coeff_eqn",
            "polytropic_efficiency_eqn",
            "Ma_con",
            "rspeed_con",
            "eff_p_v_cons",
            "polytropic_correlation",
            "delta_enth_polytropic_con",
            "mass_flow_coeff_eqn",
            "psi_3_eqn",
            "psi_s_eqn"]

        # deactivate unit model level constraints
        for c in self.component_objects(pyo.Constraint, descend_into=True):
            if c.local_name in constraint_list:
                c.deactivate()

        state_args = {
            'flow_mol': self.vapor_inlet.flow_mol[0].value,
            'pressure': self.vapor_inlet.pressure[0].value,
            'enth_mol': self.vapor_inlet.enth_mol[0].value
        }

        flags = self.control_volume.initialize(
            state_args=state_args, hold_state=True)
        super().initialize(
            state_args=state_args, outlvl=outlvl, solver=solver, optarg=optarg)

        self.efficiency_isentropic.unfix()
        for t in self.flowsheet().config.time:
            if unfix_ratioP.get(t, False):
                self.ratioP[t].unfix()
        # Activate special constraints
        for c in constraint_list:
            getattr(self, c).activate()

        with idaeslog.solver_log(solve_log, idaeslog.DEBUG) as slc:
            res = opt.solve(self, tee=slc.tee)
        self.control_volume.release_state(flags=flags, outlvl=outlvl)
        init_log.info(
            "Initialization Complete: {}".format(idaeslog.condition(res))
        )
