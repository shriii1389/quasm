# name: text after the endif that ends a skip is still an error
# expect_error: Syntax Error
set c = 1
if c == 0
endif now
endif
end
