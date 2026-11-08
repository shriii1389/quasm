# name: measure and reprepare inside a loop, five collapses
qubit a[2]
repeat 5
qubitop1 a[0] = H
qubitop2 a[0],a[1] = CN
measure a
endrepeat
print(a)
end
