#!/usr/bin/env bash
# Existing Habitat 0.1.7 build; no simulator rebuild or old project dependency.
NAVCODE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAVCODE_SIM_BUILD="${NAVCODE_SIM_BUILD:-/home1/gmh/linyuze/NaVILA/habitat-sim-0.1.7/build}"
NAVCODE_HABITAT_LAB="${NAVCODE_HABITAT_LAB:-/home1/gmh/linyuze/NaVILA/habitat-lab}"
export PYTHONPATH="${NAVCODE_ROOT}:${NAVCODE_HABITAT_LAB}:${NAVCODE_SIM_BUILD}/lib.linux-x86_64-cpython-310:${NAVCODE_SIM_BUILD}/deps/magnum-bindings/src/python${PYTHONPATH:+:$PYTHONPATH}"
export MAGNUM_LOG=quiet HABITAT_SIM_LOG=quiet
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
