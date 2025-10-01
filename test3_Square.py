#!/usr/bin/env python3
"""
Automated test script:
  – ramps a programmable power-supply 5 → 9 V in 1 V steps
  – measures the actual output with a DMM at every step
  – keeps a 1 kHz / 1 Vpp *square* wave on the function generator
"""

import pyvisa
import time

RESOURCE_NAMES = {
    "PS":   'PS1',
    "DMM":  'Multimeter',
    "FGEN": 'FGEN',
}

def idn(instr):
    try:
        return instr.query('*IDN?').strip()
    except pyvisa.VisaIOError as e:
        return f"IDN failed: {e}"

def init_instruments(rm: pyvisa.ResourceManager):
    inst = {}
    for key, alias in RESOURCE_NAMES.items():
        try:
            inst[key] = rm.open_resource(alias)
            inst[key].timeout = 5000
        except pyvisa.VisaIOError as e:
            raise SystemExit(f"Cannot open {alias}") from e
    return inst


def configure_fgen(fgen):
    """1 kHz, 0 V ÷ 1 V square wave on CH1."""
    fgen.write('*RST')
    fgen.write('FUNC SQU')              # square wave
    fgen.write('FREQ 2000')             # 1 kHz
    fgen.write('UNIT:VOLT HIGHL')       # select HIGH/LOW entry mode
    fgen.write('VOLT:HIGH 1.0')         # high level = 1 V
    fgen.write('VOLT:LOW 0.0')          # low  level = 0 V
    fgen.write('FUNC:SQU:DCYC 50')      # 50 % duty (optional)
    fgen.write('OUTP1 ON')
#time.sleep(3)
def configure_ps(ps):
    ps.write('*RST')
    ps.write('I1 2')
    ps.write('OP1 0')

def read_dmm_dc(dmm):
    try:
        dmm.write('CONF:VOLT:DC 10')
        time.sleep(0.2)
        return float(dmm.query('READ?'))
    except (pyvisa.VisaIOError, ValueError):
        return float('nan')

# ------------------------------------------------------------------
def main():
    rm   = pyvisa.ResourceManager()
    inst = init_instruments(rm)

    print("=== IDN ======================================")
    for k, v in inst.items():
        print(f"{k}: {idn(v)}")

    configure_fgen(inst['FGEN'])
    configure_ps(inst['PS'])

    print("\n=== sweep start ==============================")
    for v_set in range(2, 12):
        inst['PS'].write(f'V1 {v_set}')
        inst['PS'].write('OP1 1')
        time.sleep(2)

        reply  = inst['PS'].query('V1?').strip()
        v_ps   = float(reply.split()[-1])
        v_dmm  = read_dmm_dc(inst['DMM'])

        print(f"Set: {v_set:2d} V | PS: {v_ps:6.3f} V | DMM: {v_dmm:6.3f} V")

    print("\n=== shutdown =================================")
    inst['PS'].write('OP1 0')
    inst['FGEN'].write('OUTP1 OFF')
    for i in inst.values():
        i.close()

if __name__ == '__main__':
    main()