# name: statements may be indented
qubit q[2]
set c = 1
repeat 2
    qubitop1 q[0] = H
    if c == 1
        qubitop2 q[0],q[1] = CN
    else
        qubitop1 q[1] = X
    endif
endrepeat
    print(q)
end
