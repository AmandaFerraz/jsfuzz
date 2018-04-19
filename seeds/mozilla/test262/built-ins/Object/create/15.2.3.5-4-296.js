// Copyright (c) 2012 Ecma International.  All rights reserved.
// This code is governed by the BSD license found in the LICENSE file.

/*---
es5id: 15.2.3.5-4-296
description: >
    Object.create - 'set' property of one property in 'Properties' is
    a primitive string value (8.10.5 step 8.b)
---*/


assert.throws(TypeError, function() {
            Object.create({}, {
                prop: {
                    set: "abc"
                }
            });
});

reportCompare(0, 0);