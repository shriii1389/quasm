# SN is sqrt(NOT), so SN twice is X
qubit a = [(0.6,0.25),(0.3,-0.7)]
qubitop1 a[0] = SN
qubitop1 a[0] = SN
print(a)
end
