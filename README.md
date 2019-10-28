
# The utilities for GPU test

Add `gpu_test_tools/bin` to the `PATH` environment variable, then you can run below commands in anywhere.

----------

## run_try_job

Run try jobs that is defined in `try_job.json`, and generate test reports after test is finished.

One typical example is as below. The Chrome directory is `chromium`, the Aquarium directory is `aquarium`, the build directories of both are `out/Default`:
> run_try_job -t default -c ./chromium -a ./aquarium

```
run_try_job [--type {release,debug,default}]
            [--chrome-dir CHROME_DIR]
            [--aquarium-dir AQUARIUM_DIR]
            [--build]
            [--sync]
            [--email]
            [--iris]

optional arguments:
  --type {release,debug,default}, -t
                        Browser type. Default is 'release'.
                        release/debug/default assume that the binaries are
                        generated into out/Release or out/Debug or out/Default.
                        
  --chrome-dir CHROME_DIR, -c
                        Chrome source directory.
                        
  --aquarium-dir AQUARIUM_DIR, -a
                        Aquarium source directory.
                        
  --build, -b           Rebuild before running tests.
                        
  --sync, -s            Fetch latest source code and rebuild before running tests.
                        
  --email, -e           Send the report by email.
                        
  --iris                Enable Iris driver. (Only available on Ubuntu/Mesa environment)
```

-------

## run_gpu_test

The most import arguments are `target`, `backend`, `type`, `dir`.

The following command runs WebGL2 conformance test with ANGLE's OpenGL backend, the Chrome directory is `chromium`, the build directory is `out/Default`:

> run_gpu_test webgl2 -b gl -t default -d ./chromium 

```
run_gpu_test {webgl,webgl2,angle,fyi,aquarium}
             [--backend {gl,vulkan,d3d9,d3d11,d3d9v,d3d11v,d3d12,desktop
                         end2end,perf,pixel,dawn_d3d12,dawn_vulkan}]
             [--type {release,debug,default}]
             [--dir DIR]
             [--log]
             [--iris]
             [--filter FILTER]
             [--repeat REPEAT]
             [--shard SHARD]
             [--index INDEX]

positional arguments: {webgl,webgl2,angle,fyi,aquarium}
                        Specify the test you want to run.
                        
                        webgl    :  WebGL conformance tests
                        webgl2   :  WebGL2 conformance tests
                        angle    :  ANGLE tests
                        fyi      :  Miscellaneous less important tests
                        aquarium :  Aquarium tests

optional arguments:
  --backend {gl,vulkan,d3d9,d3d11,d3d9v,d3d11v,d3d12,desktop,
             end2end,perf,pixel,dawn_d3d12,dawn_vulkan}, -b
                        Specify the backend. Not all targets are supporting all backends.
                        Run default tests if the backend is not specified.
                        
                        [WebGL/WebGL2]
                        gl      : opengl passthrough
                        vulkan  : vulkan passthrough
                        d3d9    : d3d9   passthrough
                        d3d11   : d3d11  passthrough
                        d3d9v   : d3d9   validating
                        d3d11v  : d3d11  validating
                        desktop : use desktop GL
                        
                        [ANGLE]
                        end2end : end2end test
                        perf    : performance test
                        
                        [FYI]
                        pixel : pixel skia gold test
                        
                        [Aquarium]
                        d3d12       : d3d12
                        dawn_d3d12  : dawn d3d12
                        dawn_vulkan : dawn vulkan

  --type {release,debug,default}, -t
                        Browser type. Default is 'release'.
                        release/debug/default assume that the binaries are
                        generated into out/Release or out/Debug or out/Default.
                        
  --dir DIR, -d         Chrome/Aquarium directory.
                        
  --log, -l             Print full test logs when test is running.
                        
  --iris                Enable Iris driver. (Only available on Ubuntu/Mesa environment)
                        
  --filter FILTER, -f
                        Keywords to match the test cases. Devide with |.
                        
  --repeat REPEAT, -r
                        The number of times to repeat running this test.
                        If the number of shards is more than 1, the running sequence
                        will be shard0 * N times, shard1 * N times ...
                        
  --shard SHARD, -s
                        Total number of shards being used for this test. Default is 1.
                        
  --index INDEX, -i
                        Shard index of this test.
                        If the number of shards is more than 1 and this argument is not
                        specified, all shards will be ran in sequence.
```
--------
## parse_result

Parse test results and generate report

```
parse_result [{webgl,angle,fyi,aquarium}]
             [--dir DIR] 

positional arguments: {webgl,angle,fyi,aquarium}
                        Specify the test results you want to parse.
                        
                        webgl    :  WebGL and WebGL2 conformance tests
                        angle    :  ANGLE tests
                        fyi      :  Miscellaneous less important tests
                        aquarium :  Aquarium tests
                        

optional arguments:
  --dir DIR, -d         The directory where the results locate in.
```

----------

## build_chrome

Chrome build tools

```
build_chrome [{sync,build,pack,rev}]
             [--type {release,debug,default}]
             [--dir DIR]
             [--pack-dir PACK_DIR]

positional arguments: {sync,build,pack,rev}
                        Specify the command. Default is 'build'.
                        Can specify multiple commands at the same time.
                        
                        sync   :  fetch latest source code
                        build  :  build targets
                        pack   :  package executables that can run independently
                        rev    :  get Chrome revision

optional arguments:
  --type {release,debug,default}, -t
                        Browser type. Default is 'release'.
                        release/debug/default assume that the binaries are
                        generated into out/Release or out/Debug or out/Default.
                        
  --dir DIR, -d         Chrome source directory.
                        
  --pack-dir PACK_DIR, -p
                        Destnation directory, used by the command 'pack'.
```

----------

## build_aquarium

Aquarium build tools

```
build_aquarium [{sync,build,pack,rev}]
               [--type {release,debug,default}]
               [--dir DIR]
               [--pack-dir PACK_DIR]

positional arguments: {sync,build,pack,rev}
                        Specify the command. Default is 'build'.
                        Can specify multiple commands at the same time.
                        
                        sync   :  fetch latest source code
                        build  :  build targets
                        pack   :  package executables that can run independently
                        rev    :  get the commit ID of Aquarium and Dawn
                        

optional arguments:
  --type {release,debug,default}, -t
                        Browser type. Default is 'release'.
                        release/debug/default assume that the binaries are
                        generated into out/Release or out/Debug or out/Default.
                        
  --dir DIR, -d DIR     Aquarium source directory.
                        
  --pack-dir PACK_DIR, -p
                        Destnation directory, used by the command 'pack'.
```