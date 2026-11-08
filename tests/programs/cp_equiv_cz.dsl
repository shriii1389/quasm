# name: CP1 is CZ, CP2 applied twice is CP1
qubit a = [(0.1,0.2),(0.3,-0.4),(-0.5,0.6),(0.7,0.8)]
qubitop2 a[0],a[1] = CP1
print(a)
qubit b = [(0.1,0.2),(0.3,-0.4),(-0.5,0.6),(0.7,0.8)]
qubitop2 b[0],b[1] = CP2
qubitop2 b[0],b[1] = CP2
print(b)
end
