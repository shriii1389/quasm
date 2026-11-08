# trailing text after endrepeat
# expect_error: Syntax Error
qubit a[1]
repeat 2
qubitop1 a[0] = X
endrepeat now
end
