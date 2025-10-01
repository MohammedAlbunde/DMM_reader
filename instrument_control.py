import pyvisa
import time

def initialize_instruments():
    """Initialize connection to all three instruments"""
    rm = pyvisa.ResourceManager()
    
    # Find instruments (adjust addresses if needed)
    resources = rm.list_resources()
    print("Available instruments:", resources)
    """
    # Connect to instruments
    power_supply = None
    oscilloscope = None
    multimeter = None
    
    for resource in resources:
        try:
            instr = rm.open_resource(resource)
            idn = instr.query("*IDN?").strip()
            print(f"Found: {idn}")
            
            if "SORENSEN" in idn:
                power_supply = instr
                print("✓ Power supply connected")
            elif "TEKTRONIX" in idn:
                oscilloscope = instr
                print("✓ Oscilloscope connected")
            elif "Keysight" in idn or "34460A" in idn:
                multimeter = instr
                print("✓ Multimeter connected")
                
        except Exception as e:
            print(f"Error connecting to {resource}: {e}")
            continue
    
    return power_supply, oscilloscope, multimeter

def setup_power_supply(power_supply, voltage, current):
    Configure power supply with voltage and current limits
    try:
        # Set voltage
        power_supply.write(f"VOLT {voltage}")
        # Set current limit
        power_supply.write(f"CURR {current}")
        # Enable output
        power_supply.write("OUTP ON")
        
        print(f"Power supply set to: {voltage}V, {current}A")
        
        # Verify settings
        actual_voltage = float(power_supply.query("MEAS:VOLT?"))
        actual_current = float(power_supply.query("MEAS:CURR?"))
        print(f"Actual output: {actual_voltage:.2f}V, {actual_current:.3f}A")
        
    except Exception as e:
        print(f"Error setting power supply: {e}")

def measure_oscilloscope(oscilloscope):
    Measure voltage with oscilloscope
    try:
        # Auto-scale
        oscilloscope.write("AUTOSet EXECute")
        time.sleep(2)
        
        # Measure peak-to-peak voltage
        vpp = float(oscilloscope.query("MEASUrement:MEAS1:VALue?"))
        # Measure frequency
        freq = float(oscilloscope.query("MEASUrement:MEAS2:VALue?"))
        
        print(f"Oscilloscope measurements:")
        print(f"  Peak-to-peak voltage: {vpp:.3f}V")
        print(f"  Frequency: {freq:.1f}Hz")
        
        return vpp, freq
        
    except Exception as e:
        print(f"Error reading oscilloscope: {e}")
        return None, None

def measure_multimeter(multimeter):
    Measure DC voltage with multimeter
    try:
        # Configure for DC voltage measurement
        multimeter.write("CONF:VOLT:DC")
        # Take measurement
        voltage = float(multimeter.query("READ?"))
        
        print(f"Multimeter DC voltage: {voltage:.6f}V")
        return voltage
        
    except Exception as e:
        print(f"Error reading multimeter: {e}")
        return None

def main():
    print("=== Instrument Control System ===\n")
    
    # Initialize instruments
    power_supply, oscilloscope, multimeter = initialize_instruments()
    
    if not power_supply:
        print("❌ Power supply not found!")
        return
    
    print("\n=== Configuration ===")
    
    # Get user input
    try:
        voltage = float(input("Enter desired voltage (V): "))
        current = float(input("Enter current limit (A): "))
        
        print(f"\nSetting power supply to {voltage}V, {current}A...")
        setup_power_supply(power_supply, voltage, current)
        
        # Wait for power supply to stabilize
        time.sleep(1)
        
        print("\n=== Measurements ===")
        
        # Measure with multimeter
        if multimeter:
            measure_multimeter(multimeter)
        
        # Measure with oscilloscope
        if oscilloscope:
            measure_oscilloscope(oscilloscope)
        
        # Keep running until user stops
        print("\nPress Ctrl+C to exit...")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    except ValueError:
        print("Invalid input! Please enter numeric values.")
    finally:
        # Cleanup
        if power_supply:
            power_supply.write("OUTP OFF")
            print("Power supply output disabled")
        
        # Close connections
        for instr in [power_supply, oscilloscope, multimeter]:
            if instr:
                instr.close()

if __name__ == "__main__":
    main()
"""