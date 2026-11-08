# name: remeasuring a collapsed qubit repeats the first outcome
qubit a[1]
qubitop1 a[0] = H
measure a[0]
measure a[0]
measure a[0]
print(a)
end
