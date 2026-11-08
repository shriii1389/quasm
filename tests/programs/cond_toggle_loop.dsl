# name: a loop whose branch alternates on a classical variable
set c = 0
qubit a[1]
repeat 4
if c == 0
qubitop1 a[0] = X
set c = 1
else
qubitop1 a[0] = Y
set c = 0
endif
endrepeat
print(a)
end
