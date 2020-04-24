
# Utilities for GPU Test

This repository provides the utilities to run conformance test and unit test for GPU based on Chromium/Dawn/ANGLE/Aquarium. The tests comply with the arguments of Chromium's official trybots and simulate their actions.

## Run tryjobs

If you just want to run some type of tryjobs like official trybots and to check the results, `run_tryjob` is the only command you need to know. It runs selected tests with your local build. Once the tests are finished, the statistics are output to the screen and the file *tryjob_report.txt*.


```
run_tryjob.py [--job [webgl webgpu dawn angle gpu aquarium] ]
              [--test-filter [TEST_FILTER ...] ]
              [--result-dir RESULT_DIR]
              [--chrome-dir CHROME_DIR]
              [--dawn-dir DAWN_DIR]
              [--angle-dir ANGLE_DIR]
              [--aquarium-dir AQUARIUM_DIR]
              [--target TARGET]
```

#### Specify the tryjobs to run: --job/--test-filter
- Use the job type. You can select one or multiple jobs from the candidates, like `--job webgl dawn angle`.
- Or use the test filter. You can specify one or multiple filters, the tests that contains the filter will be run, like `--test-filter webgl2 angle_end2end`. For detailed test names, please refer to following section.
- If you don't specify tryjob with either way, all tryjobs except Aquarium will be run.
- Please note that the test filter will suppress the job type.

#### Specify the result directory: --result-dir
- This is where to hold the test logs and test results. The final report *tryjob_report.txt* is generated here as well.
- This is also the directory to run tests actually. So the coredumps or any intermediate files may be left here.
- If you leave this argument empty, it will create a directory with timestamp (like YEAR_DATE_TIME_SECOND) under the *tryjob/* subdirectory of this repository.

#### Specify the source directry: --chrome-dir, --dawn-dir, --angle-dir
- Chrome source is necessary to run WebGL/WebGPU/GPU tests.
- Chrome source supports to run Dawn/ANGLE tests as well. But the test will prefer standalone Dawn/ANGLE source to Chrome source if you specified them both.
- It's possible to specify sererated source directories for different type of tryjobs.

#### Specify the target build directory under *out/*: --target
- Please specify the basename only, like *Default* or *Release_x64*.
- If you leave this argument empty, it assumes that your local build directory is *Default*.
- If you want to specify sererated source directories, e.g. `--chrome-dir CHROME_DIR --angle-dir ANGLE_DIR`, please make sure the target build directories under these source directories are the same.

#### Examples:
- Run Dawn tests only, the target build directory is *Release*.  
  `run_try_job.py --job dawn -dawn-dir DAWN_DIR --target Release`
- Run WebGPU and Dawn tests with separated source directory  
  `run_try_job.py --job webgpu dawn --chrome-dir CHROME_DIR --dawn-dir DAWN_DIR`
- Run end2end tests of Dawn and ANGLE  
  `run_try_job.py --test-filter angle_end2end dawn_end2end --chrome-dir CHROME_DIR`
- Run WebGL and WebGPU tests and save the results to specific directory  
  `run_try_job.py --job webgl webgpu --chrome-dir CHROME_DIR --result-dir RESULT_DIR`

## Supporting tests
- WebGL
  - webgl_conformance_tests
  - webgl_conformance_validating_tests
  - webgl_conformance_gl_passthrough_tests
  - webgl_conformance_d3d9_passthrough_tests
  - webgl_conformance_vulkan_passthrough_tests
  - webgl2_conformance_tests
  - webgl2_conformance_validating_tests
  - webgl2_conformance_gl_passthrough_tests
- WebGPU
  - webgpu_blink_web_tests
- Dawn
  - dawn_end2end_tests
  - dawn_end2end_wire_tests
  - dawn_end2end_validation_layers_tests
  - dawn_perf_tests
- ANGLE
  - angle_end2end_tests
  - angle_perf_tests
- GPU
  - gl_tests
  - vulkan_tests
- Aquarium
  - aquarium_dawn_vulkan_tests
  - aquarium_dawn_d3d12_tests
  - aquarium_d3d12_tests

## Miscellaneous
- Add `gpu_test_tools/bin` to the `PATH` environment variable, then you can run commands directly in anywhere on both of Windows and Linux. For example, you can run `run_tryjob` instead of `python gpu_test_tools/run_tryjob.py`.
