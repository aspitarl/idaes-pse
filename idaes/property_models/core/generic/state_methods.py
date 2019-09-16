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
Methods for setting up state variables in generic property packages.
"""
from pyomo.environ import Constraint, NonNegativeReals, Var

from idaes.core import MaterialFlowBasis


def FPTx(b):
    # FTPx formulation always requires a flash, so set flag to True
    # TODO: should have some checking to make sure developers implement this properly
    b.always_flash = True

    # Get bounds if provided
    try:
        f_bounds = b._params.config.state_bounds["flow_mol"]
    except KeyError:
        f_bounds = (None, None)

    try:
        t_bounds = b._params.config.state_bounds["temperature"]
    except KeyError:
        t_bounds = (None, None)

    try:
        p_bounds = b._params.config.state_bounds["pressure"]
    except KeyError:
        p_bounds = (None, None)

    # Add state variables
    b.flow_mol = Var(initialize=1.0,
                     domain=NonNegativeReals,
                     bounds=f_bounds,
                     doc='Component molar flowrate [mol/s]')
    b.mole_frac_comp = Var(b._params.component_list,
                           bounds=(0, None),
                           initialize=1 / len(b._params.component_list),
                           doc='Mixture mole fractions [-]')
    b.pressure = Var(initialize=101325,
                     domain=NonNegativeReals,
                     bounds=p_bounds,
                     doc='State pressure [Pa]')
    b.temperature = Var(initialize=298.15,
                        domain=NonNegativeReals,
                        bounds=t_bounds,
                        doc='State temperature [K]')

    # Add supporting variables
    b.flow_mol_phase = Var(b._params.phase_list,
                           initialize=0.5,
                           domain=NonNegativeReals,
                           bounds=f_bounds,
                           doc='Phase molar flow rates [mol/s]')

    b.mole_frac_phase_comp = Var(
        b._params.phase_list,
        b._params.component_list,
        initialize=1/len(b._params.component_list),
        bounds=(0, None),
        doc='Phase mole fractions [-]')

    b.phase_frac = Var(
        b._params.phase_list,
        initialize=1/len(b._params.phase_list),
        bounds=(0, None),
        doc='Phase fractions [-]')

    # Add supporting constraints
    if len(b._params.phase_list) == 1:
        def rule_total_mass_balance(b):
            return b.flow_mol_phase[b._params.phase_list[1]] == b.flow_mol
        b.total_flow_balance = Constraint(rule=rule_total_mass_balance)

        def rule_comp_mass_balance(b, i):
            return b.mole_frac_comp[i] == \
                b.mole_frac_phase_comp[b._params.phase_list[1], i]
        b.component_flow_balances = Constraint(b._params.component_list,
                                               rule=rule_comp_mass_balance)

        if b.config.defined_state is False:
            # applied at outlet only
            b.sum_mole_frac_out = Constraint(
                expr=1 == sum(b.mole_frac_comp[i]
                              for i in b._params.component_list))

        def rule_phase_frac(b, p):
            return b.phase_frac[p] == 1
        b.phase_fraction_constraint = Constraint(b._params.phase_list,
                                                 rule=rule_phase_frac)

    elif len(b._params.phase_list) == 2:
        # For two pahse, use Rachford-Rice formulation
        def rule_total_mass_balance(b):
            return sum(b.flow_mol_phase[p] for p in b._params.phase_list) == \
                b.flow_mol
        b.total_flow_balance = Constraint(rule=rule_total_mass_balance)

        def rule_comp_mass_balance(b, i):
            return b.flow_mol*b.mole_frac_comp[i] == sum(
                b.flow_mol_phase[p]*b.mole_frac_phase_comp[p, i]
                for p in b._params.phase_list)
        b.component_flow_balances = Constraint(b._params.component_list,
                                               rule=rule_comp_mass_balance)

        def rule_mole_frac(b):
            return sum(b.mole_frac_phase_comp[b._params.phase_list[1], i]
                       for i in b._params.component_list) -\
                sum(b.mole_frac_phase_comp[b._params.phase_list[2], i]
                    for i in b._params.component_list) == 0
        b.sum_mole_frac = Constraint(rule=rule_mole_frac)

        if b.config.defined_state is False:
            # applied at outlet only
            b.sum_mole_frac_out = \
                Constraint(expr=1 == sum(b.mole_frac_comp[i]
                           for i in b._params.component_list))

        def rule_phase_frac(b, p):
            return b.phase_frac[p]*b.flow_mol == b.flow_mol_phase[p]
        b.phase_fraction_constraint = Constraint(b._params.phase_list,
                                                 rule=rule_phase_frac)

    else:
        # Otherwise use a general formulation
        def rule_comp_mass_balance(b, i):
            return b.flow_mol*b.mole_frac_comp[i] == sum(
                b.flow_mol_phase[p]*b.mole_frac_phase_comp[p, i]
                for p in b._params.phase_list)
        b.component_flow_balances = Constraint(b._params.component_list,
                                               rule=rule_comp_mass_balance)

        def rule_mole_frac(b, p):
            return sum(b.mole_frac_phase_comp[p, i]
                       for i in b._params.component_list) == 1
        b.sum_mole_frac = Constraint(b._params.phase_list,
                                     rule=rule_mole_frac)

        if b.config.defined_state is False:
            # applied at outlet only
            b.sum_mole_frac_out = \
                Constraint(expr=1 == sum(b.mole_frac_comp[i]
                           for i in b._params.component_list))

        def rule_phase_frac(b, p):
            return b.phase_frac[p]*b.flow_mol == b.flow_mol_phase[p]
        b.phase_fraction_constraint = Constraint(b._params.phase_list,
                                                 rule=rule_phase_frac)

    # -------------------------------------------------------------------------
    # General Methods
    def get_material_flow_terms_FPTx(p, j):
        """Create material flow terms for control volume."""
        if j in b._params.component_list:
            return b.flow_mol_phase[p] * b.mole_frac_phase_comp[p, j]
        else:
            return 0
    b.get_material_flow_terms = get_material_flow_terms_FPTx

    def get_enthalpy_flow_terms_FPTx(p):
        """Create enthalpy flow terms."""
        return b.flow_mol_phase[p] * b.enth_mol_phase[p]
    b.get_enthalpy_flow_terms = get_enthalpy_flow_terms_FPTx

    def get_material_density_terms_FPTx(p, j):
        """Create material density terms."""
        if j in b._params.component_list:
            return b.dens_mol_phase[p] * b.mole_frac_phase_comp[p, j]
        else:
            return 0
    b.get_material_density_terms = get_material_density_terms_FPTx

    def get_enthalpy_density_terms_FPTx(p):
        """Create enthalpy density terms."""
        return b.dens_mol_phase[p] * b.enth_mol_phase[p]
    b.get_enthalpy_density_terms = get_enthalpy_density_terms_FPTx

    def get_material_flow_basis_FPTx():
        return MaterialFlowBasis.molar
    b.get_material_flow_basis = get_material_flow_basis_FPTx

    def define_state_vars_FPTx():
        """Define state vars."""
        return {"flow_mol": b.flow_mol,
                "mole_frac_comp": b.mole_frac_comp,
                "temperature": b.temperature,
                "pressure": b.pressure}
    b.define_state_vars = define_state_vars_FPTx

    def FPTx_initialization(b):
        if len(b._params.phase_list) == 1:
            for p in b._params.phase_list:
                b.flow_mol_phase[p].value = \
                    b.flow_mol.value

                for j in b._params.component_list:
                    b.mole_frac_phase_comp[p, j].value = \
                        b.mole_frac_comp[j].value

        else:
            # TODO : Try to find some better guesses than this
            for p in b._params.phase_list:
                b.flow_mol_phase[p].value = \
                    b.flow_mol.value / len(b._params.phase_list)

                for j in b._params.component_list:
                    b.mole_frac_phase_comp[p, j].value = \
                        b.mole_frac_comp[j].value
    b._state_initialization = FPTx_initialization

    b._state_do_not_initialize = ["sum_mole_frac_out"]
