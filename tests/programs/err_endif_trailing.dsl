# nothing may follow endif
# expect_error: Syntax Error
set c = 1
if c == 1
endif junk
end
