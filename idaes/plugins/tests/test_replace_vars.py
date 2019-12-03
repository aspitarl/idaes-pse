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
This module contains tests for the variable replace transformation.
"""

import pytest
import pyomo.environ as pyo
import idaes

__author__ = "John Eslick"

def test_1():
    # Test scalar variables
    rp = pyo.TransformationFactory("replace_variables")
    m = pyo.ConcreteModel()
    m.x = pyo.Var(initialize=2)
    m.y = pyo.Var(initialize=3)
    m.z = pyo.Var(initialize=0)
    m.c1 = pyo.Constraint(expr=m.z==m.x + m.y)
    m.e1 = pyo.Expression(expr=m.x**m.y)
    m.o1 = pyo.Objective(expr=m.y - m.x)

    assert(m.c1.body() == -5) # hope constraint arrangment is deterministic
    assert(pyo.value(m.e1) == 8)
    assert(pyo.value(m.o1) == 1)
    rp.apply_to(m, substitute=[(m.y, m.x)])
    assert(m.c1.body() == -4)
    assert(pyo.value(m.e1) == 4)
    assert(pyo.value(m.o1) == 0)

def test_2():
    # Test vector variables and sums
    rp = pyo.TransformationFactory("replace_variables")
    m = pyo.ConcreteModel()
    m.x = pyo.Var(["a", "b", "c"], initialize=2)
    m.y = pyo.Var(initialize=3)
    m.z = pyo.Var(initialize=0)
    m.c1 = pyo.Constraint(expr=m.z==m.x["a"] + m.x["b"] + m.x["c"])
    m.e1 = pyo.Expression(expr=sum(m.x[i] for i in m.x))

    assert(m.c1.body() == -6) # hope constraint arrangment is deterministic
    assert(pyo.value(m.e1) == 6)
    rp.apply_to(m, substitute=[(m.x["c"], m.y)])
    assert(m.c1.body() == -7)
    assert(pyo.value(m.e1) == 7)

def test_3():
    # Test expression in constraint
    rp = pyo.TransformationFactory("replace_variables")
    m = pyo.ConcreteModel()
    m.x = pyo.Var(["a", "b", "c"], initialize=2)
    m.y = pyo.Var(initialize=3)
    m.z = pyo.Var(initialize=0)
    m.e1 = pyo.Expression(expr=sum(m.x[i] for i in m.x))
    m.c1 = pyo.Constraint(expr=m.z==m.e1)

    assert(m.c1.body() == -6) # hope constraint arrangment is deterministic
    rp.apply_to(m, substitute=[(m.x["c"], m.y)])
    assert(m.c1.body() == -7)

def test_4():
    # Test expression in objective
    rp = pyo.TransformationFactory("replace_variables")
    m = pyo.ConcreteModel()
    m.x = pyo.Var(["a", "b", "c"], initialize=2)
    m.y = pyo.Var(initialize=3)
    m.z = pyo.Var(initialize=0)
    m.e1 = pyo.Expression(expr=sum(m.x[i] for i in m.x))
    m.c1 = pyo.Constraint(expr=m.z==m.e1)
    m.o1 = pyo.Objective(expr=m.e1)

    assert(pyo.value(m.o1) == 6)
    rp.apply_to(m, substitute=[(m.x["c"], m.y)])
    assert(pyo.value(m.o1) == 7)

def test_4():
    # Test in a hierarchical model
    rp = pyo.TransformationFactory("replace_variables")
    m = pyo.ConcreteModel()
    m.b1 = pyo.Block()
    m.b1.b2 = pyo.Block()
    x = m.b1.b2.x = pyo.Var(["a", "b", "c"], initialize=2)
    m.y = pyo.Var(initialize=3)
    m.z = pyo.Var(initialize=0)
    m.e1 = pyo.Expression(expr=sum(x[i] for i in x))
    m.b1.c1 = pyo.Constraint(expr=m.z==m.e1)
    m.o1 = pyo.Objective(expr=m.e1)

    assert(pyo.value(m.o1) == 6)
    assert(m.b1.c1.body() == -6)
    assert(pyo.value(m.e1) == 6)
    rp.apply_to(m, substitute=[(x["c"], m.y)])
    assert(pyo.value(m.o1) == 7)
    assert(m.b1.c1.body() == -7)
    assert(pyo.value(m.e1) == 7)

def test_5():
    # Test indexed var replace
    rp = pyo.TransformationFactory("replace_variables")
    m = pyo.ConcreteModel()
    m.b1 = pyo.Block()
    m.b1.b2 = pyo.Block()
    x = m.b1.b2.x = pyo.Var(["a", "b", "c"], [1,2,3], initialize=2)
    m.y = pyo.Var(["a", "b", "c", "d"], [1,2,3], initialize=3)
    m.z = pyo.Var(initialize=0)
    m.e1 = pyo.Expression(expr=sum(x[i] for i in x))
    m.b1.c1 = pyo.Constraint(expr=m.z==m.e1)
    m.o1 = pyo.Objective(expr=m.e1)

    assert(pyo.value(m.o1) == 18)
    assert(m.b1.c1.body() == -18)
    assert(pyo.value(m.e1) == 18)
    rp.apply_to(m, substitute=[(x, m.y)])
    assert(pyo.value(m.o1) == 27)
    assert(m.b1.c1.body() == -27)
    assert(pyo.value(m.e1) == 27)

def test_6():
    # Test non-variable exception
    rp = pyo.TransformationFactory("replace_variables")
    m = pyo.ConcreteModel()
    m.b1 = pyo.Block()
    m.b1.b2 = pyo.Block()
    x = m.b1.b2.x = pyo.Var(["a", "b", "c"], [1,2,3], initialize=2)
    m.y = pyo.Var(["a", "b", "c", "d"], [1,2,3], initialize=3)
    m.z = pyo.Var(initialize=0)

    with pytest.raises(TypeError):
        rp.apply_to(m, substitute=[(x, m.b1)])
    with pytest.raises(TypeError):
        rp.apply_to(m, substitute=[(m.b1, x)])

def test_7():
    # Test replace indexed by non-indexed
    rp = pyo.TransformationFactory("replace_variables")
    m = pyo.ConcreteModel()
    m.b1 = pyo.Block()
    m.b1.b2 = pyo.Block()
    x = m.b1.b2.x = pyo.Var(["a", "b", "c"], [1,2,3], initialize=2)
    m.y = pyo.Var(["a", "b", "c", "d"], [1,2,3], initialize=3)
    m.z = pyo.Var(initialize=0)

    assert x.is_indexed()
    assert not m.z.is_indexed()
    with pytest.raises(TypeError):
        rp.apply_to(m, substitute=[(x, m.z)])

def test_8():
    # Test replace indexed by indexed var that doesn't have enough/right indexes
    rp = pyo.TransformationFactory("replace_variables")
    m = pyo.ConcreteModel()
    m.b1 = pyo.Block()
    m.b1.b2 = pyo.Block()
    x = m.b1.b2.x = pyo.Var(["a", "b", "c"], [1,2,3], initialize=2)
    m.y = pyo.Var(["a", "b", "d"], [1,2,3], initialize=3)

    with pytest.raises(ValueError):
        rp.apply_to(m, substitute=[(x, m.y)])
