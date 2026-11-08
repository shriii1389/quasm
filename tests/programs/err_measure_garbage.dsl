# name: trailing text after a measure target
# expect_error: Syntax Error
qubit a[2]
measure a junk
end
