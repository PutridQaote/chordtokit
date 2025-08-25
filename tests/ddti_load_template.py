from features.ddti import DDTi
print('Loading template…')
d = DDTi()
msg = d.build_sysex([60, 64, 67, 72])
print('Sysex length:', len(msg.data), 'starts with:', msg.data[:8])