applyWorkspace();

refreshReadiness();

$('github-profile').onclick=()=>window.autosync.openGitHub().catch(error);
