# Interference: H, then Z, then H again is exactly X.
# The middle Z flips the sign of the |1> branch, and the second H turns that
# sign difference into a certainty -- amplitudes cancelling, not probabilities.
qubit a[1]
qubitop1 a[0] = H
qubitop1 a[0] = Z
qubitop1 a[0] = H
print(a)                # |1>, with no randomness anywhere

# Two nested loops: 3 x 2 = 6 applications of X, an even number, so the
# register ends up exactly where it started.
repeat 3
repeat 2
qubitop1 a[0] = X
endrepeat
endrepeat
print(a)
end
