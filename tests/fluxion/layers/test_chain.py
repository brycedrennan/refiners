import pytest
import torch

import refiners.fluxion.layers as fl
from refiners.fluxion.context import Contexts


class ContextChain(fl.Chain):
    def init_context(self) -> Contexts:
        return {"foo": {"bar": [42]}}


def module_keys(chain: fl.Chain) -> list[str]:
    return list(chain._modules.keys())  # type: ignore[reportPrivateUsage]


def test_chain_find() -> None:
    chain = fl.Chain(fl.Linear(1, 1))

    assert chain.find(fl.Linear) == chain.Linear
    assert chain.find(fl.Conv2d) is None


def test_chain_find_parent():
    chain = fl.Chain(fl.Chain(fl.Linear(1, 1)))

    assert chain.find_parent(chain.Chain.Linear) == chain.Chain
    assert chain.find_parent(fl.Linear(1, 1)) is None


def test_chain_slice() -> None:
    chain = fl.Chain(
        fl.Linear(1, 1),
        fl.Linear(1, 1),
        fl.Linear(1, 1),
        fl.Chain(
            fl.Linear(1, 1),
            fl.Linear(1, 1),
        ),
        fl.Linear(1, 1),
    )

    x = torch.randn(1, 1)
    sliced_chain = chain[1:4]

    assert len(chain) == 5
    assert len(sliced_chain) == 3
    assert chain[:-1](x).shape == (1, 1)


def test_chain_walk_stop_iteration() -> None:
    chain = fl.Chain(
        fl.Sum(
            fl.Chain(fl.Linear(1, 1)),
            fl.Linear(1, 1),
        ),
        fl.Chain(),
        fl.Linear(1, 1),
    )

    def predicate(m: fl.Module, p: fl.Chain) -> bool:
        if isinstance(m, fl.Sum):
            raise StopIteration
        return isinstance(m, fl.Linear)

    assert len(list(chain.walk(fl.Linear))) == 3
    assert len(list(chain.walk(predicate))) == 1


def test_chain_layers() -> None:
    chain = fl.Chain(
        fl.Chain(fl.Chain(fl.Chain())),
        fl.Chain(),
        fl.Linear(1, 1),
    )

    assert len(list(chain.layers(fl.Chain))) == 2
    assert len(list(chain.layers(fl.Chain, recurse=True))) == 4


def test_chain_insert() -> None:
    parent = ContextChain(fl.Linear(1, 1), fl.Linear(1, 1))
    child = fl.Chain()
    parent.insert(1, child)

    assert module_keys(parent) == ["Linear_1", "Chain", "Linear_2"]
    assert child.parent == parent
    assert child.provider.get_context("foo") == {"bar": [42]}


def test_chain_insert_negative() -> None:
    parent = fl.Chain(fl.Linear(1, 1), fl.Linear(1, 1))
    child = fl.Chain()
    parent.insert(-2, child)

    assert module_keys(parent) == ["Linear_1", "Chain", "Linear_2"]


def test_chain_insert_after_type() -> None:
    child = fl.Chain()

    parent_1 = fl.Chain(fl.Linear(1, 1), fl.Linear(1, 1))
    parent_1.insert_after_type(fl.Linear, child)
    assert module_keys(parent_1) == ["Linear_1", "Chain", "Linear_2"]

    parent_2 = fl.Chain(fl.Conv2d(1, 1, 1), fl.Linear(1, 1))
    parent_2.insert_after_type(fl.Linear, child)
    assert module_keys(parent_2) == ["Conv2d", "Linear", "Chain"]


def test_chain_insert_before_type() -> None:
    child = fl.Chain()

    parent_1 = fl.Chain(fl.Linear(1, 1), fl.Linear(1, 1))
    parent_1.insert_before_type(fl.Linear, child)
    assert module_keys(parent_1) == ["Chain", "Linear_1", "Linear_2"]

    parent_2 = fl.Chain(fl.Conv2d(1, 1, 1), fl.Linear(1, 1))
    parent_2.insert_before_type(fl.Linear, child)
    assert module_keys(parent_2) == ["Conv2d", "Chain", "Linear"]


def test_chain_insert_overflow() -> None:
    # This behaves as insert() in lists in Python.

    child = fl.Chain()

    parent_1 = fl.Chain(fl.Linear(1, 1), fl.Linear(1, 1))
    parent_1.insert(42, child)
    assert module_keys(parent_1) == ["Linear_1", "Linear_2", "Chain"]

    parent_2 = fl.Chain(fl.Linear(1, 1), fl.Linear(1, 1))
    parent_2.insert(-42, child)
    assert module_keys(parent_2) == ["Chain", "Linear_1", "Linear_2"]


def test_chain_append() -> None:
    child = fl.Chain()

    parent = fl.Chain(fl.Linear(1, 1), fl.Linear(1, 1))
    parent.append(child)
    assert module_keys(parent) == ["Linear_1", "Linear_2", "Chain"]


def test_chain_pop() -> None:
    chain = fl.Chain(fl.Linear(1, 1), fl.Conv2d(1, 1, 1), fl.Chain())

    with pytest.raises(IndexError):
        chain.pop(3)

    with pytest.raises(IndexError):
        chain.pop(-4)

    assert module_keys(chain) == ["Linear", "Conv2d", "Chain"]
    chain.pop(1)
    assert module_keys(chain) == ["Linear", "Chain"]

    chain.pop(-2)
    assert module_keys(chain) == ["Chain"]


def test_chain_remove() -> None:
    child = fl.Linear(1, 1)

    parent = fl.Chain(
        fl.Linear(1, 1),
        child,
        fl.Chain(fl.Linear(1, 1), fl.Linear(1, 1)),
    )

    assert child in parent
    assert module_keys(parent) == ["Linear_1", "Linear_2", "Chain"]

    parent.remove(child)

    assert child not in parent
    assert module_keys(parent) == ["Linear", "Chain"]


def test_chain_replace() -> None:
    chain = fl.Chain(
        fl.Linear(1, 1),
        fl.Linear(1, 1),
        fl.Chain(fl.Linear(1, 1), fl.Linear(1, 1)),
    )

    assert isinstance(chain.Chain[1], fl.Linear)
    chain.Chain.replace(chain.Chain[1], fl.Conv2d(1, 1, 1))
    assert len(chain) == 3
    assert isinstance(chain.Chain[1], fl.Conv2d)


def test_chain_structural_copy() -> None:
    m = fl.Chain(
        fl.Sum(
            fl.Linear(4, 8),
            fl.Linear(4, 8),
        ),
        fl.Linear(8, 12),
    )

    x = torch.randn(7, 4)
    y = m(x)
    assert y.shape == (7, 12)

    m2 = m.structural_copy()

    assert m.Linear == m2.Linear
    assert m.Sum.Linear_1 == m2.Sum.Linear_1
    assert m.Sum.Linear_2 == m2.Sum.Linear_2

    assert m.Sum != m2.Sum
    assert m != m2

    assert m.Sum.parent == m
    assert m2.Sum.parent == m2

    y2 = m2(x)
    assert y2.shape == (7, 12)
    torch.equal(y2, y)


def test_setattr_dont_register() -> None:
    chain = fl.Chain(fl.Linear(in_features=1, out_features=1), fl.Linear(in_features=1, out_features=1))

    with pytest.raises(expected_exception=ValueError):
        chain.foo = fl.Linear(in_features=1, out_features=1)

    assert module_keys(chain=chain) == ["Linear_1", "Linear_2"]


EXPECTED_TREE = (
    "(CHAIN)\n    ├── Linear(in_features=1, out_features=1, device=cpu, dtype=float32) (x2)\n    └── (CHAIN)\n        ├── Linear(in_features=1,"
    " out_features=1, device=cpu, dtype=float32) #1\n        └── Linear(in_features=2, out_features=1, device=cpu, dtype=float32) #2"
)


def test_debug_print() -> None:
    chain = fl.Chain(
        fl.Linear(1, 1),
        fl.Linear(1, 1),
        fl.Chain(fl.Linear(1, 1), fl.Linear(2, 1)),
    )

    assert chain._show_error_in_tree("Chain.Linear_2") == EXPECTED_TREE  # type: ignore[reportPrivateUsage]
