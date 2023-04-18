"""
Track changes of an atom
"""
from functools import wraps
from typing import Union
import warnings

from ase import Atoms
import numpy as np

from aiida import orm
from aiida.engine import calcfunction


def wraps_ase_out_of_place(func):
    """Wraps an ASE out of place operation"""

    @wraps(func)
    def inner(tracker, *args, **kwargs):
        """Inner function wrapped"""
        atoms = tracker.node.get_ase()
        aiida_kwargs = {key: to_aiida_rep(value) for key, value in kwargs.items()}
        for i, arg in enumerate(args):
            aiida_kwargs[f"arg_{i:02d}"] = to_aiida_rep(arg)

        # Create a dummy connection between the input the output using @calcfunction
        new_atoms = func(atoms, *args, **kwargs)

        @wraps(func)
        def _transform(node, **dummy_args):  # pylint:disable=unused-argument
            return orm.StructureData(ase=new_atoms)

        transform = calcfunction(_transform)

        if tracker.track_provenance:
            node = transform(tracker.node, **aiida_kwargs)
        else:
            node = _transform(tracker.node, **aiida_kwargs)

        return AtomsTracker(obj=node, atoms=new_atoms)

    return inner


wop = wraps_ase_out_of_place


def wraps_ase_inplace(func):
    """Wraps an ASE in place operation"""

    @wraps(func)
    def inner(tracker, *args, **kwargs):
        """Inner function wrapped"""
        atoms = tracker.atoms
        aiida_kwargs = {key: to_aiida_rep(value) for key, value in kwargs.items()}
        for i, arg in enumerate(args):
            aiida_kwargs[f"arg_{i:02d}"] = to_aiida_rep(arg)

        @wraps(func)
        def _transform(node, **dummy_args):  # pylint:disable=unused-argument
            # func is an inplace operation
            func(atoms, *args, **kwargs)
            return orm.StructureData(ase=atoms)

        transform = calcfunction(_transform)

        if tracker.track_provenance:
            # Call the wrapped function if we indeed tracking the provenance
            node = transform(tracker.node, **aiida_kwargs)
        else:
            node = _transform(tracker.node, **aiida_kwargs)
        # Update the current node
        tracker.node = node
        return tracker

    return inner


def to_aiida_rep(pobj):
    """
    Convert to AiiDA representation and serialization.

    The return object is not guaranteed to fully deserialize back to the input.
    A string representation is used as the fallback.
    """

    if isinstance(pobj, dict):
        return orm.Dict(dict=pobj)
    if isinstance(pobj, list):
        return orm.List(list=pobj)
    if isinstance(pobj, tuple):
        return orm.List(list=list(pobj))
    if isinstance(pobj, Atoms):
        return orm.StructureData(ase=pobj)
    if isinstance(pobj, float):
        return orm.Float(pobj)
    if isinstance(pobj, int):
        return orm.Int(pobj)
    if isinstance(pobj, str):
        return orm.Str(pobj)
    if isinstance(pobj, np.ndarray):
        data = orm.ArrayData()
        data.set_array("array", pobj)
        return data
    warnings.warn(f"Cannot serialise {pobj} - falling back to string representation.")
    return orm.Str(pobj)


class AtomsTracker:  # pylint: disable=too-few-public-methods
    """Tracking changes of an atom"""

    def __init__(
        self,
        obj: Union[Atoms, orm.StructureData],
        atoms: Union[Atoms, None] = None,
        track=True,
    ):
        """Instantiate"""
        if isinstance(obj, Atoms):
            self.atoms = obj
            self.node = orm.StructureData(ase=obj)
        else:
            self.node = obj
            self.atoms = obj.get_ase() if atoms is None else atoms

        self.track_provenance = track


def _populate_methods():
    """Populate the methods for the `AtomsTracker` class"""

    methods_in_place = [
        "set_cell",
        "set_positions",
        "set_pbc",
        "set_atomic_numbers",
        "set_chemical_symbols",
        "set_masses",
        "pop",
        "translate",
        "center",
        "set_center_of_mass",
        "rotate",
        "euler_rotate",
        "set_dihedral",
        "rotate_dihedral",
        "set_angle",
        "rattle",
        "set_distance",
        "set_scaled_positions",
        "wrap",
        "__delitem__",
        "__imul__",
    ]
    methods_out_of_place = ["repeat", "__getitem__", "__mul__"]

    for name in methods_in_place:
        setattr(AtomsTracker, name, wraps_ase_inplace(getattr(Atoms, name)))
    for name in methods_out_of_place:
        setattr(AtomsTracker, name, wraps_ase_out_of_place(getattr(Atoms, name)))


_populate_methods()
