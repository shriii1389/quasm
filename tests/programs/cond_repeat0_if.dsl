# name: an if inside a repeat 0 body is read and never run
qubit a[1]
repeat 0
if 1 == 1
qubitop1 a[0] = X
else
qubitop1 a[0] = Y
endif
print(a)
endrepeat
print(a)
end
