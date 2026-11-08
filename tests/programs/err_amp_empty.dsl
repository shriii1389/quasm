# an amplitude with no digits at all, which used to parse as zero
# expect_error: Syntax Error
qubit a = [(,0),(1,0)]
end
