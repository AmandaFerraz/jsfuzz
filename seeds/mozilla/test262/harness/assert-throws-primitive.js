// Copyright (C) 2015 the V8 project authors. All rights reserved.
// This code is governed by the BSD license found in the LICENSE file.

/*---
description: >
    Functions that throw primitive values do not satisfy the assertion.
includes: [sta.js]
---*/
var threw = false;

try {
  assert.throws(Error, function() {
    throw 3;
  });
} catch(err) {
  threw = true;
  if (err.constructor !== Test262Error) {
    $ERROR(
      'Expected a Test262Error, but a "' + err.constructor.name +
      '" was thrown.'
    );
  }
}

if (threw === false) {
  $ERROR('Expected a Test262Error, but no error was thrown.');
}

reportCompare(0, 0);
