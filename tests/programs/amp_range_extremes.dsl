# name: the largest and smallest magnitudes in range still measure correctly
qubit a = [(1e17,0),(1e-18,0)]
measure a[0]
print(a)
qubit b = [(9.99999999e17,0),(0,9.99999999e17)]
measure b
print(b)
end
