import pyvisa
import time
rm = pyvisa.ResourceManager()
#print (rm)  
my_instrument = rm.open_resource('PS1')
my_instrument2 = rm.open_resource('Multimeter')
my_instrument3 = rm.open_resource('FGEN')
print("RST")

# ------------------------------------------------------------------
#  FGEN – set up a 1 kHz, 1 Vpp sine on CH1
# ------------------------------------------------------------------
my_instrument3.write('*RST')                       # reset the generator
my_instrument3.write('FUNC SIN')                   # sine wave
my_instrument3.write('FREQ 1000')                  # 1 kHz
my_instrument3.write('VOLT 1.0')                   # 1 Vpp
my_instrument3.write('VOLT:OFFS 0.0')              # 0 V DC-offset
my_instrument3.write('OUTP1 ON')                   # turn CH1 output on
# ------------------------------------------------------------------
time.sleep(2)
print("RST DONE")
print(my_instrument.query('*IDN?'))
print(my_instrument2.query('MEAS:DC?'))
print(my_instrument3.query('*IDN?'))
print("Instr1= ",my_instrument)
print("Instr2= ",my_instrument2)
print("Instr3= ",my_instrument3)  
my_instrument.write('RANGE1 1')
#print(my_instrument.query('V1?'))
#time.sleep(3)
for x in range (5,10,1):
    print("PS")
    my_instrument.write('V1 '+str(x))
    print(my_instrument.query('V1?'))
    print(my_instrument2.query('MEAS:DC?'))
    
    
    time.sleep(2)

#my_instrument.write('V1 10')
my_instrument.write('I1 2')
print("PS")
#print(my_instrument.query('V1?'))
my_instrument.write('OP1 1')
time.sleep(3)
my_instrument.write('OP1 0')
my_instrument3.write('OUTP1 OFF') 
my_instrument.close()