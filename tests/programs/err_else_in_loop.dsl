# name: an else must belong to the innermost open block, which here is a loop
# expect_error: else or endif without if
set c = 0
if c == 0
repeat 2
else
endrepeat
endif
end
