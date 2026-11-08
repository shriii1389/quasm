# name: a repeat 0 inside a loop stays skipped on every replay
qubit a[1]
repeat 2
qubitop1 a[0] = X
repeat 0
qubitop1 a[0] = X
endrepeat
print(a)
endrepeat
end
