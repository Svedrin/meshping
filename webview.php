<?php

// My brother is totally gonna kill me for this

$libdir  = "/var/lib/meshping";
$instdir = "/opt/meshping";

if( !isset($_SERVER["PATH_INFO"]) || !$_SERVER["PATH_INFO"] ){
    echo "<ul>";
    foreach( scandir($libdir) as $fname ){
        if(!is_file("$libdir/$fname"))
            continue;
        echo "<li><a href=\"{$_SERVER['REQUEST_URI']}/{$fname}.png\">{$fname}</a></li>";
    }
    echo "</ul>";
}
else{
    foreach( scandir($libdir) as $fname ){
        if(!is_file("$libdir/$fname") || $_SERVER["PATH_INFO"] !== "/{$fname}.png")
            continue;
        header("Content-Type: image/png");
        passthru("python $instdir/histodraw.py \"$libdir/$fname\" -");
    }
}
