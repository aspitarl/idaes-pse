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
Tests for generic property package core code

Author: Andrew Lee
"""
import pytest
from sys import modules

from pyomo.environ import Block, ConcreteModel, Set
from pyomo.common.config import ConfigBlock, ConfigValue

from idaes.property_models.core.generic.generic_property import (
        GenericPropertyPackageError,
        get_method,
        GenericParameterData,
        GenericStateBlock)

from idaes.core import declare_process_block_class
from idaes.core.util.exceptions import ConfigurationError, PropertyPackageError
from idaes.core.util.misc import add_object_reference


# -----------------------------------------------------------------------------
supported_properties = ["phase_component_list",
                        "state_bounds",
                        "phase_equilibrium_formulation",
                        "phase_equilibrium_dict",
                        "bubble_temperature",
                        "dew_temperature",
                        "bubble_pressure",
                        "dew_pressure",
                        "dens_mol_liq_comp",
                        "enth_mol_liq_comp",
                        "enth_mol_ig_comp",
                        "entr_mol_liq_comp",
                        "entr_mol_ig_comp",
                        "pressure_sat_comp"]


# -----------------------------------------------------------------------------
def test_GenericPropertyPackageError():
    with pytest.raises(PropertyPackageError):
        raise GenericPropertyPackageError("block", "prop")


# Dummy method for testing get_method
def dummy_option(b):
    return b.dummy_response


class TestGetMethod(object):
    @pytest.fixture(scope="class")
    def frame(self):
        m = ConcreteModel()

        # Create a dummy parameter block
        m.params = Block()

        # Add necessary parameters to parameter block
        m.params.config = ConfigBlock()
        m.params.config.declare("dummy_option", ConfigValue(default=None))

        # Create a dummy state block
        m.props = Block([1])
        m.props[1].config = ConfigBlock()
        add_object_reference(m.props[1], "_params", m.params)

        m.props[1].dummy_response = "foo"

        return m

    def test_None(self, frame):
        with pytest.raises(GenericPropertyPackageError):
            get_method(frame.props[1], "dummy_option")

    def test_invlaid_option(self, frame):
        with pytest.raises(AttributeError):
            get_method(frame.props[1], "foo")

    def test_method(self, frame):
        # Test that get_method works when provided with the method directly
        frame.params.config.dummy_option = dummy_option

        assert get_method(frame.props[1], "dummy_option") is dummy_option
        assert get_method(frame.props[1], "dummy_option")(frame.props[1]) is \
            frame.props[1].dummy_response

    def test_module(self, frame):
        # Test that get_method works when pointed to a module with the method
        frame.params.config.dummy_option = modules[__name__]

        assert get_method(frame.props[1], "dummy_option") is dummy_option
        assert get_method(frame.props[1], "dummy_option")(frame.props[1]) is \
            frame.props[1].dummy_response

    def test_not_method_or_module(self, frame):
        # Test that get_method works when provided with the method directly
        frame.params.config.dummy_option = "foo"

        with pytest.raises(ConfigurationError):
            get_method(frame.props[1], "dummy_option")


# -----------------------------------------------------------------------------
@declare_process_block_class("DummyParameterBlock")
class DummyParameterData(GenericParameterData):
    def configure(self):
        self.configured = True

    def parameters(self):
        self.parameters_set = True


class TestGenericParameterBlock(object):
    def test_configure(self):
        m = ConcreteModel()
        m.params = DummyParameterBlock(default={
                "component_list": ["a", "b", "c"],
                "phase_list": [1, 2],
                "state_definition": "foo",
                "equation_of_state": {1: "foo", 2: "bar"}})

        assert m.params.config.component_list == ["a", "b", "c"]
        assert m.params.config.phase_list == [1, 2]
        assert m.params.config.state_definition == "foo"
        assert m.params.config.equation_of_state == {1: "foo", 2: "bar"}

        # Tesrt number of config arguments. Note 1 inherited argument
        assert len(m.params.config) == len(supported_properties) + 4 + 1

        for i in supported_properties:
            assert m.params.config[i] is None

        assert m.params.configured

    def test_configure_no_components(self):
        m = ConcreteModel()

        with pytest.raises(ConfigurationError,
                           match="params Generic Property Package was not "
                           "provided with a component_list."):
            m.params = DummyParameterBlock()

    def test_configure_no_phases(self):
        m = ConcreteModel()

        with pytest.raises(ConfigurationError,
                           match="params Generic Property Package was not "
                           "provided with a phase_list."):
            m.params = DummyParameterBlock(default={
                "component_list": ["a", "b", "c"]})

    def test_configure_invalid_phase_comp_1(self):
        # Phase-component list with invalid phase
        m = ConcreteModel()

        with pytest.raises(ConfigurationError,
                           match="params Generic Property Package provided "
                           "with invalid phase_component_list. Phase 3 is not "
                           "a member of phase_list."):
            m.params = DummyParameterBlock(default={
                "component_list": ["a", "b", "c"],
                "phase_list": [1, 2],
                "phase_component_list": {1: ["a", "b", "c"],
                                         2: ["a", "b", "c"],
                                         3: ["a", "b", "c"]}})

    def test_configure_invalid_phase_comp_2(self):
        # Phase-component list with invalid component
        m = ConcreteModel()

        with pytest.raises(ConfigurationError,
                           match="params Generic Property Package provided "
                           "with invalid phase_component_list. Component d in "
                           "phase 1 is not a members of component_list."):
            m.params = DummyParameterBlock(default={
                "component_list": ["a", "b", "c"],
                "phase_list": [1, 2],
                "phase_component_list": {1: ["a", "b", "c", "d"],
                                         2: ["a", "b", "c", "d"]}})

    def test_configure_only_phase_equilibrium_formulation(self):
        m = ConcreteModel()

        with pytest.raises(ConfigurationError,
                           match="params Generic Property Package provided "
                           "with only one of phase_equilibrium_formulation and"
                           " phase_equilibrium_dict. Either both of these "
                           "arguments need to be provided or neither."):
            m.params = DummyParameterBlock(default={
                "component_list": ["a", "b", "c"],
                "phase_list": [1, 2],
                "state_definition": "foo",
                "equation_of_state": {1: "foo", 2: "bar"},
                "phase_equilibrium_formulation": "foo"})

    def test_configure_only_phase_equilibrium_dict(self):
        m = ConcreteModel()

        with pytest.raises(ConfigurationError,
                           match="params Generic Property Package provided "
                           "with only one of phase_equilibrium_formulation and"
                           " phase_equilibrium_dict. Either both of these "
                           "arguments need to be provided or neither."):
            m.params = DummyParameterBlock(default={
                "component_list": ["a", "b", "c"],
                "phase_list": [1, 2],
                "state_definition": "foo",
                "equation_of_state": {1: "foo", 2: "bar"},
                "phase_equilibrium_dict": {}})

    def test_configure_invalid_phase_equilibrium_dict_1(self):
        # Not dict
        m = ConcreteModel()

        with pytest.raises(ConfigurationError,
                           match="params Generic Property Package provided "
                           "with invalid phase_equilibrium_dict - value must "
                           "be a dict. Please see the documentation for the "
                           "correct form."):
            m.params = DummyParameterBlock(default={
                "component_list": ["a", "b", "c"],
                "phase_list": [1, 2],
                "state_definition": "foo",
                "equation_of_state": {1: "foo", 2: "bar"},
                "phase_equilibrium_formulation": "foo",
                "phase_equilibrium_dict": "foo"})

    def test_configure_invalid_phase_equilibrium_dict_2(self):
        # Value not list
        m = ConcreteModel()

        with pytest.raises(ConfigurationError,
                           match="params Generic Property Package provided "
                           "with invalid phase_equilibrium_dict, foo. "
                           "Values in dict must be lists containing 2 "
                           "values."):
            m.params = DummyParameterBlock(default={
                "component_list": ["a", "b", "c"],
                "phase_list": [1, 2],
                "state_definition": "foo",
                "equation_of_state": {1: "foo", 2: "bar"},
                "phase_equilibrium_formulation": "foo",
                "phase_equilibrium_dict": {1: "foo"}})

    def test_configure_invalid_phase_equilibrium_dict_3(self):
        # List with wrong number of values
        m = ConcreteModel()

        # Matching error text has been challenging for some reason
        with pytest.raises(ConfigurationError):
            m.params = DummyParameterBlock(default={
                "component_list": ["a", "b", "c"],
                "phase_list": [1, 2],
                "state_definition": "foo",
                "equation_of_state": {1: "foo", 2: "bar"},
                "phase_equilibrium_formulation": "foo",
                "phase_equilibrium_dict": {1: [1, 2, 3]}})

    def test_configure_invalid_phase_equilibrium_dict_4(self):
        # First value not component
        m = ConcreteModel()

        with pytest.raises(ConfigurationError,
                           match="params Generic Property Package provided "
                           "with invalid phase_equilibrium_dict. First value "
                           "in each list must be a valid component, recieved "
                           "foo."):
            m.params = DummyParameterBlock(default={
                "component_list": ["a", "b", "c"],
                "phase_list": [1, 2],
                "state_definition": "foo",
                "equation_of_state": {1: "foo", 2: "bar"},
                "phase_equilibrium_formulation": "foo",
                "phase_equilibrium_dict": {1: ["foo", "bar"]}})

    def test_configure_invalid_phase_equilibrium_dict_5(self):
        # Second value tuple
        m = ConcreteModel()

        with pytest.raises(ConfigurationError,
                           match="params Generic Property Package provided "
                           "with invalid phase_equilibrium_dict. Second value "
                           "in each list must be a 2-tuple containing 2 valid "
                           "phases, recieved bar."):
            m.params = DummyParameterBlock(default={
                "component_list": ["a", "b", "c"],
                "phase_list": [1, 2],
                "state_definition": "foo",
                "equation_of_state": {1: "foo", 2: "bar"},
                "phase_equilibrium_formulation": "foo",
                "phase_equilibrium_dict": {1: ["a", "bar"]}})

    def test_configure_invalid_phase_equilibrium_dict_6(self):
        # Second value tuple, but wrong length
        m = ConcreteModel()

        # String matching difficult again
        with pytest.raises(ConfigurationError):
            m.params = DummyParameterBlock(default={
                "component_list": ["a", "b", "c"],
                "phase_list": [1, 2],
                "state_definition": "foo",
                "equation_of_state": {1: "foo", 2: "bar"},
                "phase_equilibrium_formulation": "foo",
                "phase_equilibrium_dict": {1: ["a", (1, 2, 3)]}})

    def test_configure_invalid_phase_equilibrium_dict_7(self):
        # Invalid phase in tuple
        m = ConcreteModel()

        # String matching difficult again
        with pytest.raises(ConfigurationError):
            m.params = DummyParameterBlock(default={
                "component_list": ["a", "b", "c"],
                "phase_list": [1, 2],
                "state_definition": "foo",
                "equation_of_state": {1: "foo", 2: "bar"},
                "phase_equilibrium_formulation": "foo",
                "phase_equilibrium_dict": {1: ["a", (1, 3)]}})

    def test_configure_phase_equilibrium(self):
        # Invalid phase in tuple
        m = ConcreteModel()

        # String matching difficult again
        m.params = DummyParameterBlock(default={
                "component_list": ["a", "b", "c"],
                "phase_list": [1, 2],
                "state_definition": "foo",
                "equation_of_state": {1: "foo", 2: "bar"},
                "phase_equilibrium_formulation": "foo",
                "phase_equilibrium_dict": {1: ["a", (1, 2)]}})

        assert m.params.phase_equilibrium_list == \
            m.params.config.phase_equilibrium_dict
        assert isinstance(m.params.phase_equilibrium_idx, Set)
        assert len(m.params.phase_equilibrium_idx) == \
            len(m.params.config.phase_equilibrium_dict)
        for k in m.params.phase_equilibrium_idx:
            assert k in m.params.config.phase_equilibrium_dict.keys()
