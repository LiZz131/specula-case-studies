source $(dirname "$(realpath "$0")")/../../../scripts/env.sh && export CUR_SCRIPT_DIR=$(eval $(get_dir_cmd)) && export_more
export testcase_generator_py=$(dirname "$CUR_SCRIPT_DIR")/testcase_generator.py
export SANDTABLE_SCRIPTS=/root/sandtable/scripts
