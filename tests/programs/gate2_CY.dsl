# CY with control q0 and target q1
qubit q = [(0.1,0.2),(0.3,-0.4),(-0.5,0.6),(0.7,0.8)]
qubitop2 q[0],q[1] = CY
print(q)
end
