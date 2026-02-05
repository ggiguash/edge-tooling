package main

import (
	"flag"
	"os"
	"path/filepath"
	"strings"

	"github.com/kevinburke/ssh_config"
)

var (
	hostName     string
	identityFile string
	user         string
	key          string
)

func main() {
	sshConfigPath := filepath.Join(os.Getenv("HOME"), ".ssh", "config")
	flag.StringVar(&key, "k", "", "host key to update")
	flag.StringVar(&hostName, "h", "", "hostname")
	flag.StringVar(&identityFile, "i", "", "identity file path")
	flag.StringVar(&user, "u", "", "user")
	flag.Parse()

	f, err := os.Open(sshConfigPath)
	if err != nil {
		panic(err)
	}
	cfg, err := ssh_config.Decode(f)
	if err != nil {
		panic(err)
	}

	for _, host := range cfg.Hosts {
		if !host.Matches(key) {
			continue
		}
		for _, node := range host.Nodes {
			switch t := node.(type) {
			case *ssh_config.KV:
				if user != "" && strings.ToLower(t.Key) == "user" {
					t.Value = user
				}
				if hostName != "" && strings.ToLower(t.Key) == "hostname" {
					t.Value = hostName
				}
				if identityFile != "" && strings.ToLower(t.Key) == "identityfile" {
					t.Value = identityFile
				}
			}
		}
	}

	bits, _ := cfg.MarshalText()
	if err := os.WriteFile(sshConfigPath, bits, 0644); err != nil {
		panic(err)
	}
}
