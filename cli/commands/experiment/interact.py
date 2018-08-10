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

import sys
import time
from pathlib import Path
from typing import List, Tuple

import click
from tabulate import tabulate

from cli_state import common_options, pass_state, State
from commands.experiment.submit import HELP_P
from util.aliascmd import AliasCmd
from util.k8s.k8s_info import get_kubectl_current_context_namespace, check_pods_status, PodStatus
from util.launcher import launch_app
from util.app_names import DLS4EAppNames
from commands.experiment.common import submit_experiment, RUN_MESSAGE, RUN_NAME, RUN_PARAMETERS, RUN_STATUS, \
    JUPYTER_NOTEBOOK_TEMPLATE_NAME
from util.exceptions import SubmitExperimentError, LaunchError, ProxyClosingError
from util.logger import initialize_logger
from platform_resources.experiments import get_experiment, generate_name
from commands.experiment.common import check_experiment_name
from util.exceptions import K8sProxyCloseError

HELP = "Launches a local browser with Jupyter Notebook. If the script name argument " \
       "is given, then script is put into the opened notebook."
HELP_N = "The name of this Jupyter Notebook session."
HELP_F = "File with a notebook that should be opened in Jupyter notebook."
HELP_PO = "Port on which service will be exposed locally."


JUPYTER_CHECK_POD_READY_TRIES = 60

log = initialize_logger(__name__)


@click.command(short_help=HELP, cls=AliasCmd, alias='i')
@click.option('-n', '--name', default=None, help=HELP_N)
@click.option('-f', '--filename', default=None, help=HELP_F)
@click.option("-p", "--pack_param", type=(str, str), multiple=True, help=HELP_P)
@click.option('--no-launch', is_flag=True, help='Run command without a web browser starting, '
                                                'only proxy tunnel is created')
@click.option('-pn', '--port_number', type=click.IntRange(1024, 65535), help=HELP_PO)
@common_options()
@pass_state
def interact(state: State, name: str, filename: str, pack_param: List[Tuple[str, str]], no_launch: bool,
             port_number: int):
    """
    Starts an interactive session with Jupyter Notebook.
    """
    current_namespace = get_kubectl_current_context_namespace()
    create_new_notebook = True

    jupyter_experiment = None

    if name:
        try:
            jupyter_experiment = get_experiment(namespace=current_namespace, name=name)
        except Exception:
            err_message = "Problems during loading a list of experiments."
            log.exception(err_message)
            click.echo(err_message)
            sys.exit(1)

        # if experiment exists and is not based on jupyter image - we need to ask a user to choose another name
        if jupyter_experiment and jupyter_experiment.template_name != JUPYTER_NOTEBOOK_TEMPLATE_NAME:
            click.echo(f"The chosen name ({name}) is already used by an experiment other than Jupyter Notebook. "
                       f"Please choose another one")
            sys.exit(1)

        if not jupyter_experiment and not click.confirm("Experiment with a given name doesn't exist. "
                                                        "Should the app continue and create a new one? "):
            sys.exit(0)

        if jupyter_experiment:
            create_new_notebook = False
        else:
            try:
                check_experiment_name(value=name)
            except click.BadParameter as exe:
                click.echo(str(exe))
                sys.exit(1)

    number_of_retries = 0
    if create_new_notebook:
        number_of_retries = 5
        try:
            exp_name = name
            if not name and not filename:
                exp_name = generate_name("jup")

            click.echo("Submitting interactive experiment.")
            runs, filename = submit_experiment(script_location=filename, script_folder_location=None,
                                               template=JUPYTER_NOTEBOOK_TEMPLATE_NAME,
                                               name=exp_name, parameter_range=[], parameter_set=(),
                                               script_parameters=(), pack_params=pack_param)
            click.echo(tabulate({RUN_NAME: [run.name for run in runs],
                                 RUN_PARAMETERS: [run.formatted_parameters() for run in runs],
                                 RUN_STATUS: [run.formatted_status() for run in runs],
                                 RUN_MESSAGE: [run.error_message for run in runs]},
                                headers=[RUN_NAME, RUN_PARAMETERS, RUN_STATUS, RUN_MESSAGE], tablefmt="orgtbl"))
            if runs:
                name = runs[0].name
            else:
                # run wasn't created - error
                raise RuntimeError("Run wasn't created")

        except K8sProxyCloseError as exe:
            click.echo(exe.message)
        except SubmitExperimentError as exe:
            err_message = f"Error during starting jupyter notebook session: {exe.message}"
            log.exception(err_message)
            click.echo(err_message)
            sys.exit(1)
        except Exception:
            err_message = "Other error during starting jupyter notebook session."
            log.exception(err_message)
            click.echo(err_message)
            sys.exit(1)
    else:
        # if jupyter service exists - the system only connects to it
        click.echo("Jupyter notebook's session exists. dlsctl connects to this session ...")

    url_end = ""
    if filename:
        # only Jupyter notebooks are opened directly, other files are opened in edit mode
        if not jupyter_experiment:
            if ".ipynb" in filename:
                url_end = "/notebooks/"
            else:
                url_end = "/edit/"
            url_end = url_end + Path(filename).name
        else:
            click.echo("Attaching script to existing Jupyter notebook's session is not supported. "
                       "Please create a new Jupyter notebook's session to attach script.")

    # wait until all jupyter pods are ready
    for i in range(JUPYTER_CHECK_POD_READY_TRIES):
        try:
            if check_pods_status(run_name=name, namespace=current_namespace, status=PodStatus.RUNNING):
                break
        except Exception:
            log.exception("Error during checking state of Jupyter notebook.")
        time.sleep(1)
    else:
        click.echo("Jupyter notebook is still not ready. Please try to connect to it by running"
                   "interact command another time passing a name of a current Jupyter notebook session")
        sys.exit(1)

    try:
        launch_app(k8s_app_name=DLS4EAppNames.JUPYTER, app_name=name, no_launch=no_launch,
                   number_of_retries=number_of_retries, url_end=url_end, port=port_number)
    except LaunchError as exe:
        log.exception(exe.message)
        click.echo(exe.message)
        sys.exit(1)
    except ProxyClosingError:
        click.echo('K8s proxy hasn\'t been closed properly. '
                   'Check whether it still exists, if yes - close it manually.')
    except Exception:
        err_message = "Other exception during launching interact session."
        log.exception(err_message)
        click.echo(err_message)
        sys.exit(1)
