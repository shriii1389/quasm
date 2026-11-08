# a malformed redeclaration must leave the existing register completely
# untouched -- not partially overwritten before the trailing-garbage check
# fails
# expect_error: (0.70710677,0.0),(0.70710677,0.0)
qubit q[1]
qubitop1 q[0] = H
qubit q = [(1,0),(0,0)] junk
print(q)
end
