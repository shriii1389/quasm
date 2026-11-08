# name: rebinding a classical variable changes which branch runs
set c = 1
qubit a[1]
if c == 1
qubitop1 a[0] = X
endif
set c = 2
if c == 1
qubitop1 a[0] = X
else
qubitop1 a[0] = H
endif
print(a)
end
