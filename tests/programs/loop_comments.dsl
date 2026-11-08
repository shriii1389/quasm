# name: comments and blank lines inside a replayed loop body
qubit a[2]

repeat 2

# a whole-line comment in the body
qubitop1 a[0] = H       # and a trailing one
qubitop2 a[0],a[1] = CN

endrepeat
print(a)                # two passes of H then CN, checked against the oracle
end
