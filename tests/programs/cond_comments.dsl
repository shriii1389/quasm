# name: comments and blank lines inside both branches
set c = 0
qubit a[1]
if c == 1        # not this one

qubitop1 a[0] = X

else             # this one

# a comment in the taken branch
qubitop1 a[0] = H

endif
print(a)
end
