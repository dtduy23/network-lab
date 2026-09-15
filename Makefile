.PHONY: bootstrap doctor up provision verify test integration report halt clean
bootstrap:
	./labctl bootstrap
doctor:
	./labctl doctor
up:
	./labctl up
provision:
	./labctl provision
verify:
	./labctl verify
test:
	./labctl test
integration:
	./labctl integration
report:
	./labctl report
halt:
	./labctl halt
clean:
	./labctl destroy
