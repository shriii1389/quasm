# name: a tiny but nonzero register measures normally; the guard is relative
qubit a = [(0.00001,0),(0,0)]
measure a[0]
print(a)
qubit b = [(0,0),(0,0.000001),(0,0),(0,0)]
measure b
print(b)
end
