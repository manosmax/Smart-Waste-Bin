/**
 * This is the default settings file provided by Node-RED.
 *
 * It can contain any valid JavaScript code that will get run when Node-RED
 * is started.
 *
 * Lines that start with // are commented out.
 * Each entry should be separated from the entries above and below by a comma ','
 *
 * For more information about individual settings, refer to the documentation:
 *    https://nodered.org/docs/user-guide/runtime/configuration
 *
 * The settings are split into the following sections:
 *  - Flow File and User Directory Settings
 *  - Security
 *  - Server Settings
 *  - Runtime Settings
 *  - Editor Settings
 *  - Node Settings
 *
 **/


module.exports = {


/*******************************************************************************
 * Flow File and User Directory Settings
 *  - flowFile
 *  - credentialSecret
 *  - flowFilePretty
 *  - userDir
 *  - nodesDir
 ******************************************************************************/


    /** The file containing the flows. If not set, defaults to flows_<hostname>.json **/
    flowFile: 'flows.json',


    /** By default, credentials are encrypted in storage using a generated key. To
     * specify your own secret, set the following property.
     * If you want to disable encryption of credentials, set this property to false.
     * Note: once you set this property, do not change it - doing so will prevent
     * node-red from being able to decrypt your existing credentials and they will be
     * lost.
     */
    credentialSecret: "team8key",   // ← CHANGE THIS to your own secret


    /** By default, the flow JSON will be formatted over multiple lines making
     * it easier to compare changes when using version control.
     * To disable pretty-printing of the JSON set the following property to false.
     */
    flowFilePretty: true,


    /** By default, all user data is stored in a directory called `.node-red` under
     * the user's home directory. To use a different location, the following
     * property can be used
     */
    //userDir: '/home/nol/.node-red/',


    /** Node-RED scans the `nodes` directory in the userDir to find local node files.
     * The following property can be used to specify an additional directory to scan.
     */
    //nodesDir: '/home/nol/.node-red/nodes',


/*******************************************************************************
 * Security
 *  - adminAuth
 *  - https
 *  - httpsRefreshInterval
 *  - requireHttps
 *  - httpNodeAuth
 *  - httpStaticAuth
 ******************************************************************************/


    /** To password protect the Node-RED editor and admin API, the following
     * property can be used. See https://nodered.org/docs/security.html for details.
     */
    //adminAuth: {
    //    type: "credentials",
    //    users: [{
    //        username: "admin",
    //        password: "$2a$08$zZWtXTja0fB1pzD4sHCMyOCMYz2Z6dNbM6tl8sJogENOMcxWV9DN.",
    //        permissions: "*"
    //    }]
    //},


    /** The following property can be used to enable HTTPS
     * This property can be either an object, containing both a (private) key
     * and a (public) certificate, or a function that returns such an object.
     * See http://nodejs.org/api/https.html#https_https_createserver_options_requestlistener
     * for details of its contents.
     */

    /** Option 1: static object */
    //https: {
    //  key: require("fs").readFileSync('privkey.pem'),
    //  cert: require("fs").readFileSync('cert.pem')
    //},

    /** Option 2: function that returns the HTTP configuration object */
    // https: function() {
    //     return {
    //         key: require("fs").readFileSync('privkey.pem'),
    //         cert: require("fs").readFileSync('cert.pem')
    //     }
    // },

    //httpsRefreshInterval : 12,
    //requireHttps: true,
    //httpNodeAuth: {user:"user",pass:"$2a$08$zZWtXTja0fB1pzD4sHCMyOCMYz2Z6dNbM6tl8sJogENOMcxWV9DN."},
    //httpStaticAuth: {user:"user",pass:"$2a$08$zZWtXTja0fB1pzD4sHCMyOCMYz2Z6dNbM6tl8sJogENOMcxWV9DN."},


/*******************************************************************************
 * Server Settings
 ******************************************************************************/

    uiPort: process.env.PORT || 1880,

    //uiHost: "127.0.0.1",
    //apiMaxLength: '5mb',
    //httpServerOptions: { },
    //httpAdminRoot: '/admin',
    //httpNodeRoot: '/red-nodes',
    //httpNodeCors: {
    //    origin: "*",
    //    methods: "GET,PUT,POST,DELETE"
    //},
    //httpStatic: '/home/nol/node-red-static/',
    //httpStaticRoot: '/static/',


/*******************************************************************************
 * Runtime Settings
 ******************************************************************************/

    diagnostics: {
        enabled: true,
        ui: true,
    },

    runtimeState: {
        enabled: false,
        ui: false,
    },

    telemetry: {
        // enabled: true,
        // updateNotification: true
    },

    logging: {
        console: {
            level: "info",
            metrics: false,
            audit: false
        }
    },

    //contextStorage: {
    //    default: {
    //        module:"localfilesystem"
    //    },
    //},

    exportGlobalContextKeys: false,

    externalModules: {
        autoInstall: true,        // ← automatically installs missing modules on startup
        autoInstallRetry: 30,
        palette: {
            allowInstall: true,
            allowUpdate: true,
            allowUpload: true,
            allowList: ['*'],
            denyList: [],
            allowUpdateList: ['*'],
            denyUpdateList: []
        },
        modules: {
            allowInstall: true,
            allowList: ['*'],
            denyList: []
        }
    },


/*******************************************************************************
 * Editor Settings
 ******************************************************************************/

    editorTheme: {
        palette: {
            //categories: ['subflows', 'common', 'function', 'network', 'sequence', 'parser', 'storage'],
        },

        projects: {
            enabled: false,
            workflow: {
                mode: "manual"
            }
        },

        codeEditor: {
            lib: "monaco",
            options: {
                // theme: "vs",
                //fontSize: 14,
                //fontFamily: "Cascadia Code, Fira Code, Consolas, 'Courier New', monospace",
                //fontLigatures: true,
            }
        },

        markdownEditor: {
            mermaid: {
                enabled: true
            }
        },

        multiplayer: {
            enabled: false
        },
    },


/*******************************************************************************
 * Node Settings
 ******************************************************************************/

    //fileWorkingDirectory: "",

    functionExternalModules: true,

    globalFunctionTimeout: 0,

    functionTimeout: 0,

    functionGlobalContext: {
        // os:require('os'),
    },

    //nodeMessageBufferMaxLength: 0,

    //ui: { path: "ui" },

    //debugUseColors: true,

    debugMaxLength: 1000,

    //debugStatusLength: 32,

    //execMaxBufferSize: 10000000,

    //httpRequestTimeout: 120000,

    mqttReconnectTime: 15000,

    serialReconnectTime: 15000,

    //socketReconnectTime: 10000,
    //socketTimeout: 120000,
    //tcpMsgQueueSize: 2000,
    //inboundWebSocketTimeout: 5000,
    //tlsConfigDisableLocalFiles: true,

    // nodeDefaults: {
    //     "debug": {
    //         "complete": true
    //     }
    // }
}
