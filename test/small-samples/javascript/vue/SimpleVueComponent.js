export default {
    name: 'SimpleVueComponent',
    data() {
        return {
            message: 'Hello Vue'
        };
    },
    methods: {
        greet() {
            return this.message;
        },
        sayHi() {
            console.log('Hi!');
        }
    },
    mounted() {
        this.greet();
    }
};
