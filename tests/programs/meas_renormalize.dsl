# name: uneven amplitudes, collapse divides by sqrt(p)
qubit a = [(0.6,0),(0,0.8)]
print(a)
measure a[0]
print(a)
end
