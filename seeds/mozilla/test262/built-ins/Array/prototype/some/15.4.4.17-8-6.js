// Copyright (c) 2012 Ecma International.  All rights reserved.
// This code is governed by the BSD license found in the LICENSE file.

/*---
esid: sec-array.prototype.some
es5id: 15.4.4.17-8-6
description: >
    Array.prototype.some returns false if 'length' is 0 (subclassed
    Array, length overridden with obj with valueOf)
---*/

  foo.prototype = new Array(1, 2, 3);
  function foo() {}
  var f = new foo();

  var o = { valueOf: function () { return 0;}};
  f.length = o;

  function cb(){}
  var i = f.some(cb);


assert.sameValue(i, false, 'i');

reportCompare(0, 0);
