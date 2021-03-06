// Copyright (c) 2012 Ecma International.  All rights reserved.
// This code is governed by the BSD license found in the LICENSE file.

/*---
es5id: 12.10.1-1-s
description: with statement in strict mode throws SyntaxError (strict function)
flags: [noStrict]
---*/


assert.throws(SyntaxError, function() {
    // wrapping it in eval since this needs to be a syntax error. The
    // exception thrown must be a SyntaxError exception.
    eval("\
          function f() {\
            \'use strict\';\
            var o = {}; \
            with (o) {};\
          }\
        ");
});

reportCompare(0, 0);
