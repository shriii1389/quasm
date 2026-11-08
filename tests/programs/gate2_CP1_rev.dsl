# CP1 with the control and target the other way round
qubit q = [(0.1,0.2),(0.3,-0.4),(-0.5,0.6),(0.7,0.8)]
qubitop2 q[1],q[0] = CP1
print(q)
end
