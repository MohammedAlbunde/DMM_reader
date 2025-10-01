#!/usr/bin/env python3
"""
Automated test script:
  – ramps a programmable power-supply from 5 V → 9 V in 1 V steps
  – measures the actual output with a DMM at every step
  – keeps a 1 kHz / 1 Vpp sine running on the function generator
"""

import pyvisa
import time

RESOURCE_NAMES = {          # <-- edit these strings to match your VISA aliases
    "PS":      'PS1',        # power supply
    "DMM":     'Multimeter',# 6½-digit DMM
    "FGEN":    'FGEN',      # Keysight Trueform 33500/33600
}

def idn(instr):
    """Return *IDN? string safely."""
    try:
        return instr.query('*IDN?').strip()
    except pyvisa.VisaIOError as e:
        return f"IDN failed: {e}"

def init_instruments(rm: pyvisa.ResourceManager):
    """Open all three instruments and return a dict."""
    inst = {}
    for key, alias in RESOURCE_NAMES.items():
        try:
            inst[key] = rm.open_resource(alias)
            inst[key].timeout = 5000          # 5 s global timeout
        except pyvisa.VisaIOError as e:
            raise SystemExit(f"Cannot open {alias} – check VISA aliases / cables") from e
    return inst

def configure_fgen(fgen):
    """1 kHz, 1 Vpp sine on CH1."""
    fgen.write('*RST')
    fgen.write('FUNC SIN')
    fgen.write('FREQ 1000')
    fgen.write('VOLT 1.0')
    fgen.write('VOLT:OFFS 0')
    fgen.write('OUTP1 ON')

def configure_ps(ps):
    """Basic PS set-up (example for a TTi or similar)."""
    ps.write('*RST')
    ps.write('I1 2')          # 2 A current limit
    ps.write('OP1 0')         # output OFF for now

def read_dmm_dc(dmm):
    """
    Read DC voltage.
    Many Keysight/Agilent DMMs need CONF:VOLT:DC once, then just READ?
    MEAS:DC? is a shorthand, but *only* if the range is already appropriate.
    """
    try:
        dmm.write('CONF:VOLT:DC 10')   # 10 V range (auto if you prefer)
        time.sleep(0.2)                # let relay settle
        return float(dmm.query('READ?'))
    except (pyvisa.VisaIOError, ValueError) as e:
        print(f"DMM read error: {e}")
        return float('nan')

# ------------------------------------------------------------------
# Main
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
    for v_set in range(5, 10):            # 5 .. 9 V
        inst['PS'].write(f'V1 {v_set}')
        inst['PS'].write('OP1 1')         # enable output
        time.sleep(1)                     # let things settle

        # ---- fixed read-back for Sorensen XDL ----
        reply = inst['PS'].query('V1?').strip()  # e.g. 'V1 5.000'
        v_ps = float(reply.split()[-1])          # take last token

        v_dmm = read_dmm_dc(inst['DMM'])

        print(f"Set: {v_set:2d} V | PS reads: {v_ps:6.3f} V | DMM reads: {v_dmm:6.3f} V")

    print("\n=== shutdown =================================")
    inst['PS'].write('OP1 0')             # output OFF
    inst['FGEN'].write('OUTP1 OFF')
    for i in inst.values():
        i.close()

if __name__ == '__main__':
    main()