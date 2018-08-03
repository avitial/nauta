#
# INTEL CONFIDENTIAL
# Copyright (c) 2018 Intel Corporation
#
# The source code contained or described herein and all documents related to
# the source code ("Material") are owned by Intel Corporation or its suppliers
# or licensors. Title to the Material remains with Intel Corporation or its
# suppliers and licensors. The Material contains trade secrets and proprietary
# and confidential information of Intel or its suppliers and licensors. The
# Material is protected by worldwide copyright and trade secret laws and treaty
# provisions. No part of the Material may be used, copied, reproduced, modified,
# published, uploaded, posted, transmitted, distributed, or disclosed in any way
# without Intel's prior express written permission.
#
# No license under any patent, copyright, trade secret or other intellectual
# property right is granted to or conferred upon you by disclosure or delivery
# of the Materials, either expressly, by implication, inducement, estoppel or
# otherwise. Any license under such intellectual property rights must be express
# and approved by Intel in writing.
#

from unittest.mock import MagicMock

from click.testing import CliRunner
import pytest

from commands.predict import launch


class LaunchPredictMocks:
    def __init__(self, mocker):
        self.generate_name_mock = mocker.patch('commands.predict.launch.generate_name')
        self.start_inference_instance_mock = mocker.patch('commands.predict.launch.start_inference_instance')
        self.get_inference_instance_url_mock = mocker.patch('commands.predict.launch.get_inference_instance_url')
        self.get_authorization_header_mock = mocker.patch('commands.predict.launch.get_authorization_header')


@pytest.fixture
def launch_mocks(mocker):
    mocks = LaunchPredictMocks(mocker=mocker)
    return mocks


def test_launch(launch_mocks: LaunchPredictMocks):
    model_location = '/fake/model/location'
    name = 'fake-model-name'

    runner = CliRunner()
    runner.invoke(launch.launch, ['--model-location', model_location, '--name', name])

    assert launch_mocks.generate_name_mock.call_count == 0
    assert launch_mocks.start_inference_instance_mock.call_count == 1
    assert launch_mocks.get_inference_instance_url_mock.call_count == 1
    assert launch_mocks.get_authorization_header_mock.call_count == 1


def test_launch_generate_name(launch_mocks: LaunchPredictMocks):
    model_location = '/fake/model/location'

    runner = CliRunner()
    runner.invoke(launch.launch, ['--model-location', model_location])

    assert launch_mocks.generate_name_mock.call_count == 1
    assert launch_mocks.start_inference_instance_mock.call_count == 1
    assert launch_mocks.get_inference_instance_url_mock.call_count == 1
    assert launch_mocks.get_authorization_header_mock.call_count == 1


def test_launch_fail(launch_mocks: LaunchPredictMocks):
    launch_mocks.start_inference_instance_mock.side_effect = RuntimeError

    model_location = '/fake/model/location'

    runner = CliRunner()
    result = runner.invoke(launch.launch, ['--model-location', model_location])

    assert launch_mocks.generate_name_mock.call_count == 1
    assert launch_mocks.start_inference_instance_mock.call_count == 1
    assert launch_mocks.get_inference_instance_url_mock.call_count == 0
    assert launch_mocks.get_authorization_header_mock.call_count == 0
    assert result.exit_code == 1


def test_launch_url_fail(launch_mocks: LaunchPredictMocks):
    launch_mocks.get_inference_instance_url_mock.side_effect = RuntimeError

    model_location = '/fake/model/location'

    runner = CliRunner()
    result = runner.invoke(launch.launch, ['--model-location', model_location])

    assert launch_mocks.generate_name_mock.call_count == 1
    assert launch_mocks.start_inference_instance_mock.call_count == 1
    assert launch_mocks.get_inference_instance_url_mock.call_count == 1
    assert launch_mocks.get_authorization_header_mock.call_count == 0
    assert result.exit_code == 1


def test_start_inference_instance(mocker):
    submit_experiment_mock = mocker.patch('commands.predict.launch.submit_experiment')
    fake_experiment = MagicMock()
    submit_experiment_mock.return_value = [fake_experiment], 'fake_path'

    inference_instance = launch.start_inference_instance(name='', model_location='', model_name='')

    assert inference_instance == fake_experiment