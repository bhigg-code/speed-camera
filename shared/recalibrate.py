import json

with open('C:/speedcamera/config.json', 'r') as f:
    config = json.load(f)

old_cal = config['pixels_per_foot']
measured = 28.4
actual = 25.0
new_cal = old_cal * (measured / actual)

config['pixels_per_foot'] = round(new_cal, 2)
config['calibration_note'] = f'Calibrated from drive-by: measured {measured} mph at actual {actual} mph'

with open('C:/speedcamera/config.json', 'w') as f:
    json.dump(config, f, indent=2)

print(f'Old calibration: {old_cal} px/ft')
print(f'New calibration: {config["pixels_per_foot"]} px/ft')
print(f'Adjustment: {(measured/actual - 1)*100:.1f}% correction')
