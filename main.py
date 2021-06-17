import json
import os
import shutil
import stat
import subprocess as sp
import sys
from os import listdir
from os.path import isfile, join

import chevron
import git

from clone import CloneProgress


def deploy_build_directory(build_path, moodle_path):
    dirs = build_path.rsplit("/")
    plugin_name = dirs[-1].split("_build")
    shutil.copytree(build_path, moodle_path + plugin_name[0])


def write_to_file(filename, content):
    f = open(filename, "w")
    f.write(content)
    f.close()


def update_password(filename, password):
    with open(filename, 'r') as f:
        content = chevron.render(f, {'password': password})
    write_to_file(filename, content)


def insert_build_variables(filename, key, value):
    with open(filename, 'r') as f:
        content = chevron.render(f, {key: value})
    write_to_file(filename, content)


def build_angular_app():
    os.chdir("./build/moodle-charts")
    print("Installing Angular Dependencies")
    sp.call("npm install", shell=True)
    print("BUILDING")
    sp.call("ng build --prod", shell=True)
    print("BUILT")
    print("SLEEP")
    os.chdir("../../")


def get_angular_prod_resource_names(resources):
    path = os.path.abspath('./build/moodle-charts/dist/moodle-charts/')
    files = [f for f in listdir(path) if isfile(join(path, f))]

    results = list(filter(lambda filename: filename.count(".") == 2, files))
    for result in results:
        filename = result[0:result.find('.')]
        if filename == 'styles':
            resources['styles'] = result
        elif filename == 'polyfills':
            resources['polyfills'] = result
        elif filename == 'polyfills-es5':
            resources['polyfills-es5'] = result
        elif filename == 'runtime':
            resources['runtime'] = result
        elif filename == 'main':
            resources['main'] = result
    return resources


def mustachio_file(filename, resources):
    with open(filename, 'r') as f:
        content = chevron.render(f, resources)
    write_to_file(filename, content)


def create_zip_archive(output_filename, root, base):
    try:
        shutil.make_archive(output_filename, 'zip', root, base)
    except FileNotFoundError:
        print("%s not found" % base)


def get_config_from_file(path=None):
    if path is None:
        f = open('config.json', )
    else:
        f = open(path, )
    data = json.load(f)
    for i in data:
        print(i)
    f.close()
    return data


def clean(path='./build/'):
    try:
        shutil.rmtree(path)
        os.makedirs(path)
    except FileNotFoundError:
        print("%s not found" % path)


def update_config_file(path, config):
    if path is None:
        f = open('config.json', 'w')
    else:
        f = open(path, 'w')

    with f as outfile:
        json.dump(config, outfile)


def on_rm_error(func, path, exc_info):
    # from: https://stackoverflow.com/questions/4829043/how-to-remove-read-only-attrib-directory-with-python-in-windows
    os.chmod(path, stat.S_IWRITE)
    os.unlink(path)


if __name__ == '__main__':
    clean()
    clean('./output/')
    path = sys.argv[1] if len(sys.argv) >= 2 else None
    config = get_config_from_file(path)

    ad_config = config['repositories']['analytics_dashboard']
    mc_config = config['repositories']['moodle_charts']
    ws_config = config['repositories']['web_service']
    ca_config = config['repositories']['course_analytics']

    print("Cloning repo=%s" % (ad_config['git']))
    git.Repo.clone_from(ad_config['git'], './build/' + ad_config['name'], branch='hotfix/filenames_lnu',
                        progress=CloneProgress())

    print("Cloning repo=%s" % (mc_config['git']))
    git.Repo.clone_from(mc_config['git'], './build/' + mc_config['name'], branch='hotfix/build_improvements',
                        progress=CloneProgress())

    print("Cloning repo=%s" % (ws_config['git']))
    git.Repo.clone_from(ws_config['git'], './build/' + ws_config['name'], branch='hotfix/token_lnu',
                        progress=CloneProgress())

    print("Cloning repo=%s" % (ca_config['git']))
    git.Repo.clone_from(ca_config['git'], './build/' + ca_config['name'], branch='hotfix/build_automation',
                        progress=CloneProgress())

    print("Updating Angular prod environment config")
    angular_build_resources = {"moodle_webservice_api_key": config['angular']['web_service_token'],
                               "angular_resources_location": config['angular']['web_service_host']}
    mustachio_file('./build/' + mc_config['name'] + '/src/environments/environment.prod.ts', angular_build_resources)
    build_angular_app()

    print("Updating %s config" % (ad_config['name']))
    angular_resources = get_angular_prod_resource_names(
        {"styles": '', "polyfills": '', 'polyfills-es5': '', 'runtime': '', 'main': '',
         'angular_app_location': config['angular']['angular_host']})
    mustachio_file('./build/' + ad_config['name'] + '/classes/renderable.php', angular_resources)
    insert_build_variables('./build/' + ad_config['name'] + '/token_factory.php', 'password', 'WORLD!')

    ad_config['version'] += 1
    update_config_file(path, config)
    insert_build_variables('./build/' + ad_config['name'] + '/version.php', 'version', ad_config['version'])
    print("Updating %s version" % (ad_config['version']))

    print("Updating %s config" % (ca_config['name']))
    angular_resources = get_angular_prod_resource_names(
        {"styles": '', "polyfills": '', 'polyfills-es5': '', 'runtime': '', 'main': '',
         'angular_app_location': config['angular']['angular_host']})
    mustachio_file('./build/' + ca_config['name'] + '/block_course_analytics.php', angular_resources)
    insert_build_variables('./build/' + ca_config['name'] + '/token_factory.php', 'password', 'WORLD!')

    ca_config['version'] += 1
    update_config_file(path, config)
    insert_build_variables('./build/' + ca_config['name'] + '/version.php', 'version', ca_config['version'])
    print("Updating %s version" % (ca_config['version']))

    print("Updating %s config" % (ws_config['name']))
    insert_build_variables('./build/' + ws_config['name'] + '/token_verifier.php', 'password', 'WORLD!')
    ws_config['version'] += 1
    update_config_file(path, config)
    insert_build_variables('./build/' + ws_config['name'] + '/version.php', 'version', ws_config['version'])

    print("Updating %s version" % (ws_config['version']))

    print("Creating archives of plugins")
    shutil.rmtree('./build/' + ad_config['name'] + '/.git', onerror=on_rm_error)
    shutil.rmtree('./build/' + ws_config['name'] + '/.git', onerror=on_rm_error)
    shutil.rmtree('./build/' + ca_config['name'] + '/.git', onerror=on_rm_error)
    os.remove('./build/' + ad_config['name'] + '/.gitignore')
    os.remove('./build/' + ws_config['name'] + '/.gitignore')
    os.remove('./build/' + ca_config['name'] + '/.gitignore')

    create_zip_archive('output/' + ad_config['name'], './build', ad_config['name'])
    create_zip_archive('output/' + ws_config['name'], './build', ws_config['name'])
    create_zip_archive('output/' + ca_config['name'], './build', ca_config['name'])
    create_zip_archive('output/moodle_charts', './build/' + mc_config['name'] + '/dist/', mc_config['name'])
